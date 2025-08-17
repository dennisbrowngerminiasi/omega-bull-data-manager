import json
from threading import Lock
from multiprocessing import shared_memory

import pytest

from shared_memory.shared_memory_reader import StockDataReader
from shared_memory.shared_memory_manager import SharedMemoryManager


class DummyDataManager:
    def register_listener(self, listener):
        pass

    def start_downloader_agent(self):
        pass


class FakeStockData:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.df = None
        self._data = {
            "ticker": ticker,
            "start_date": "2024-01-01",
            "cur_date": "2024-01-01",
            "end_date": "2024-01-01",
            "period": "1 D",
            "df": [],
        }

    def to_serializable_dict(self):
        return self._data


def test_get_stock_requires_configuration():
    reader = StockDataReader("127.0.0.1", 12345)
    with pytest.raises(ValueError, match="Shared memory not configured"):
        reader.get_stock("UPST")


def test_get_stock_with_layout_returns_data():
    layout = {"AAPL": [1, 2, 3]}
    reader = StockDataReader("127.0.0.1", 12345, layout=layout)
    assert reader.get_stock("AAPL") == [1, 2, 3]


def test_read_from_real_shared_memory():
    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="test_reader_shm")
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), shm)
    smm.write_data([FakeStockData("AAPL")])

    reader = StockDataReader("127.0.0.1", 12345, shm_name=shm.name)
    assert "AAPL" in reader.list_tickers()
    data = reader.get_stock("AAPL")
    assert isinstance(data, dict) and data["ticker"] == "AAPL"
    reader.close()

    shm.close()
    shm.unlink()
