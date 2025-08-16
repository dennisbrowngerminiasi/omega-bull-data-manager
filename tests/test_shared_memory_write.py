from threading import Lock

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


def test_write_data_populates_shared_memory_and_cache():
    shared_dict = {}
    lock = Lock()
    smm = SharedMemoryManager(shared_dict, lock, DummyDataManager())

    data = [FakeStockData("AAPL", 100.0, 10), FakeStockData("MSFT", 200.0, 20)]
    smm.write_data(data)

    for ticker, price in [("AAPL", 100.0), ("MSFT", 200.0)]:
        assert ticker in shared_dict
        entry = shared_dict[ticker]
        assert entry["data"]["ticker"] == ticker
        assert entry["header"]["epoch"] % 2 == 0
        assert entry["header"]["last_update_ms"] > 0
        assert smm.quote_cache[ticker]["price"] == price

    assert smm.snapshot_state["epoch"] % 2 == 0
    first_epoch = smm.snapshot_state["epoch"]

    smm.write_data(data)
    assert smm.snapshot_state["epoch"] == first_epoch + 2
