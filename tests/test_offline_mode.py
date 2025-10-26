import csv
import sys
import threading
import time
from pathlib import Path
from threading import Lock

from multiprocessing import shared_memory

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared_memory.shared_memory_manager import SharedMemoryManager
from stock.stock_data_manager import StockDataManager
from utils import paths


def test_shared_memory_hydrates_from_cached_csv(monkeypatch, tmp_path):
    # Point the CSV cache directory to an isolated temporary folder for the
    # duration of the test.
    monkeypatch.setattr(paths, "CSV_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "stock.stock_data_manager.CSV_DATA_DIR", tmp_path, raising=False
    )
    monkeypatch.setattr(
        "shared_memory.shared_memory_manager.CSV_DATA_DIR", tmp_path, raising=False
    )

    csv_path = tmp_path / "AAPL.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writerow(["2024-01-01", 10.0, 12.0, 9.5, 11.5, 1500])

    manager = StockDataManager()
    # Prevent the integration-test download path from overwriting the cached
    # data during the test and record that reconciliation was attempted when the
    # shared memory manager hydrates from disk.
    manager.start_downloader_agent = lambda: None
    reconcile_calls = []

    def _record_reconcile():
        reconcile_calls.append(True)

    manager.reconcile_offline_cache = _record_reconcile

    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="offline_test")
    try:
        SharedMemoryManager(shared_dict, lock, manager, shm)
    finally:
        shm.close()
        shm.unlink()

    assert "AAPL" in shared_dict
    cached_entry = shared_dict["AAPL"]["data"]
    assert cached_entry["ticker"] == "AAPL"
    assert cached_entry["df"][0]["Close"] == 11.5
    assert reconcile_calls, "Expected offline reconciliation to be attempted"


def test_integration_mode_skips_ibkr_connection(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(paths, "CSV_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "stock.stock_data_manager.CSV_DATA_DIR", tmp_path, raising=False
    )

    csv_path = tmp_path / "MSFT.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writerow(["2024-02-01", 100.0, 110.0, 95.0, 105.0, 2000])

    manager = StockDataManager()

    with caplog.at_level("INFO"):
        result = manager.connect_to_ibkr_tws()

    assert result is False
    assert any(
        "skipping ibkr connection" in message.lower()
        for message in caplog.messages
    )


def test_reconcile_offline_cache_appends_missing_rows(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(paths, "CSV_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "stock.stock_data_manager.CSV_DATA_DIR", tmp_path, raising=False
    )

    csv_path = tmp_path / "AAPL.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writerow(["2024-01-01", 10.0, 12.0, 9.5, 11.5, 1500])

    manager = StockDataManager()
    manager.start_downloader_agent = lambda: None

    # Pretend that the runtime is now operating outside integration mode so
    # reconciliation logic proceeds, but provide a stub incremental fetch
    # implementation so the test avoids any real market data requests.
    monkeypatch.setattr(
        "stock.stock_data_manager.INTEGRATION_TEST_MODE", False, raising=False
    )

    class _ConnectedClient:
        def isConnected(self):
            return True

    manager.ibkr_client = _ConnectedClient()
    manager.connect_to_ibkr_tws = lambda: True

    manager._determine_missing_ranges = lambda: {"AAPL": ("2024-01-02", "2024-01-02")}

    new_rows = [
        {"Date": "2024-01-02", "Open": 12.0, "High": 13.0, "Low": 11.0, "Close": 12.5, "Volume": 1800}
    ]

    class _StubStockData:
        def __init__(self, ticker):
            self.ticker = ticker

        def is_data_empty(self):
            return False

        def to_serializable_dict(self):
            return {
                "ticker": self.ticker,
                "start_date": new_rows[0]["Date"],
                "cur_date": new_rows[-1]["Date"],
                "end_date": new_rows[-1]["Date"],
                "period": "1 D",
                "df": list(new_rows),
            }

    manager._fetch_incremental_data = lambda *args, **kwargs: _StubStockData("AAPL")

    with caplog.at_level("INFO"):
        manager.reconcile_offline_cache()

    with csv_path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[-1]["Date"] == "2024-01-02"
    assert rows[-1]["Close"] == "12.5"

    cached_entries = manager.get_all_stock_data()
    assert cached_entries[0]._data["df"][-1]["Date"] == "2024-01-02"
    expected_log = "downloading incremental data for aapl from 2024-01-02 to 2024-01-02"
    assert any(
        expected_log in message.lower() for message in caplog.messages
    ), caplog.messages


def test_real_mode_downloader_runs_in_background(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "CSV_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "stock.stock_data_manager.CSV_DATA_DIR", tmp_path, raising=False
    )

    manager = StockDataManager()

    # Simulate production mode after initialization by toggling the runtime flag
    # and stubbing out the expensive download implementation.  This mirrors the
    # behaviour in the live server where the downloader runs on a background
    # thread while the main thread continues serving requests.
    monkeypatch.setattr(
        "stock.stock_data_manager.INTEGRATION_TEST_MODE", False, raising=False
    )

    start_event = threading.Event()

    def _stub_downloader(periodicity):
        start_event.set()
        return

    manager.downloader_agent = _stub_downloader

    start = time.time()
    manager.start_downloader_agent()
    duration = time.time() - start

    assert duration < 0.1, "Downloader should start asynchronously"
    assert start_event.wait(1), "Background downloader thread did not run"

    manager.stop_downloader_agent()
