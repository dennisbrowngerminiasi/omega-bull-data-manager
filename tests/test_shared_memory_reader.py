import pytest

from shared_memory.shared_memory_reader import StockDataReader


def test_get_stock_requires_configuration():
    reader = StockDataReader("127.0.0.1", 12345)
    with pytest.raises(ValueError, match="Shared memory not configured"):
        reader.get_stock("UPST")


def test_get_stock_with_layout_returns_data():
    layout = {"AAPL": [1, 2, 3]}
    reader = StockDataReader("127.0.0.1", 12345, shm_name="shm0", layout=layout)
    assert reader.get_stock("AAPL") == [1, 2, 3]
