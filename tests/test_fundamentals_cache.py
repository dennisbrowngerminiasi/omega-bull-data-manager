import time
import datetime as dt

from shared_memory.fundamentals_cache import FundamentalsCache
from server.data.fundamentals.ibkr_fundamentals import FundamentalsDTO


def test_cache_set_get_and_expiry():
    cache = FundamentalsCache(ttl_seconds=1, fresh_ttl_seconds=1)
    dto = FundamentalsDTO(
        symbol="AAPL",
        as_of=dt.datetime.utcnow(),
        source="TEST",
        report_types_used=[],
        company={},
        statements={},
        ratios={},
        cap_table={},
    )
    cache.set("AAPL", dto)
    assert cache.get("AAPL") == dto
    assert not cache.is_expired("AAPL")
    time.sleep(1.1)
    assert cache.get("AAPL") is None
    assert cache.is_expired("AAPL")
