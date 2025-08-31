from threading import Lock
from multiprocessing import shared_memory
import datetime as dt

from shared_memory.shared_memory_manager import SharedMemoryManager
from shared_memory.fundamentals_cache import FundamentalsCache
from server.data.fundamentals.ibkr_fundamentals import FundamentalsDTO


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


def test_fundamentals_embedded_in_shared_dict():
    shared_dict = {}
    lock = Lock()
    shm = shared_memory.SharedMemory(create=True, size=10_000, name="test_fund_shm")
    cache = FundamentalsCache(ttl_seconds=60, fresh_ttl_seconds=60)
    dto = FundamentalsDTO(
        symbol="AAPL",
        as_of=dt.datetime(2024, 1, 1),
        source="TEST",
        report_types_used=[],
        company={"name": "Apple"},
        statements={},
        ratios={},
        cap_table={},
    )
    cache.set("AAPL", dto)

    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager(), shm, fundamentals_cache=cache)
    smm.write_data([FakeStockData("AAPL")])

    entry = shared_dict["AAPL"]["data"]["fundamentals"]
    assert entry["company"]["name"] == "Apple"

    shm.close()
    shm.unlink()
