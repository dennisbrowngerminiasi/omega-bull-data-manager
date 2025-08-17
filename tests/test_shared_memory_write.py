from threading import Lock
import json
from datetime import datetime
import logging

from multiprocessing import shared_memory

from shared_memory.shared_memory_manager import SharedMemoryManager


class DummyDataManager:
    def register_listener(self, listener):
        pass

    def start_downloader_agent(self):
        pass


class FakeStockData:
    def __init__(self, ticker: str, price: float, volume: int, date: str = "2024-01-01"):
        self.ticker = ticker
        self.df = None  # avoid pandas dependency
        self._data = {
            "ticker": ticker,
            "start_date": date,
            "cur_date": date,
            "end_date": date,
            "period": "1 D",
            "df": [
                {
                    "Date": date,
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": volume,
                }
            ],
        }

    def to_serializable_dict(self):
        return self._data


class FakeDateTimeStockData:
    """Stock data returning datetime objects to verify JSON serialization."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.df = None
        self._data = {
            "ticker": ticker,
            "start_date": datetime(2024, 1, 1),
            "cur_date": datetime(2024, 1, 2),
            "end_date": datetime(2024, 1, 2),
            "period": "1 D",
            "df": None,
        }

    def to_serializable_dict(self):
        return self._data


def test_write_data_populates_shared_memory_and_cache():
    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="test_shm")
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), shm)

    data = [FakeStockData("AAPL", 100.0, 10), FakeStockData("MSFT", 200.0, 20)]
    smm.write_data(data)

    # Verify dictionary contents and quote cache
    for ticker, price in [("AAPL", 100.0), ("MSFT", 200.0)]:
        assert ticker in shared_dict
        entry = shared_dict[ticker]
        assert entry["data"]["ticker"] == ticker
        assert entry["header"]["epoch"] % 2 == 0
        assert entry["header"]["last_update_ms"] > 0
        assert smm.quote_cache[ticker]["price"] == price

    # Ensure payload persisted to the shared-memory segment
    raw = bytes(shm.buf).rstrip(b"\x00")
    stored = json.loads(raw.decode("utf-8"))
    assert "AAPL" in stored and "MSFT" in stored

    assert smm.snapshot_state["epoch"] % 2 == 0
    first_epoch = smm.snapshot_state["epoch"]

    smm.write_data(data)
    assert smm.snapshot_state["epoch"] == first_epoch + 2

    shm.close()
    shm.unlink()


def test_write_data_serializes_datetime_fields():
    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="test_shm_dt")
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), shm)

    smm.write_data([FakeDateTimeStockData("AAPL")])

    raw = bytes(shm.buf).rstrip(b"\x00")
    stored = json.loads(raw.decode("utf-8"))
    assert stored["AAPL"]["data"]["start_date"] == "2024-01-01T00:00:00"

    shm.close()
    shm.unlink()


def test_epoch_logging(caplog):
    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="test_shm_log")
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), shm)

    data = [FakeStockData("AAPL", 100.0, 10)]
    with caplog.at_level(logging.DEBUG):
        smm.write_data(data)

    assert any("Global epoch" in rec.message for rec in caplog.records)
    assert any("Ticker AAPL" in rec.message for rec in caplog.records)

    shm.close()
    shm.unlink()


def test_write_data_resizes_shared_memory_when_needed():
    shared_dict = {}
    lock = Lock()
    small_shm = shared_memory.SharedMemory(create=True, size=128, name="test_shm_small")
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), small_shm)

    big = FakeStockData("BIG", 1.0, 1)
    big._data["df"][0]["Extra"] = "x" * 500

    smm.write_data([big])

    assert smm.shared_mem.size > 128
    raw = bytes(smm.shared_mem.buf).rstrip(b"\x00")
    stored = json.loads(raw.decode("utf-8"))
    assert "BIG" in stored

    smm.shared_mem.close()
    smm.shared_mem.unlink()
