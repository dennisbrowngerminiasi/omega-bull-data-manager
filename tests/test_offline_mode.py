import csv
from threading import Lock

from multiprocessing import shared_memory

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
    # data during the test.
    manager.start_downloader_agent = lambda: None

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
