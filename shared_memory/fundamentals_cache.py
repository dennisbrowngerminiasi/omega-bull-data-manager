import time
from typing import Dict, Tuple, Optional, Any


class FundamentalsCache:
    """In-process cache for :class:`FundamentalsDTO` objects with TTL support."""

    def __init__(self, ttl_seconds: int, fresh_ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self._store: Dict[str, Tuple[Any, float]] = {}

    def get(self, symbol: str) -> Optional[Any]:
        item = self._store.get(symbol)
        if not item:
            return None
        obj, ts = item
        if time.time() - ts > self.ttl_seconds:
            return None
        return obj

    def set(self, symbol: str, dto: Any) -> None:
        self._store[symbol] = (dto, time.time())

    def is_expired(self, symbol: str) -> bool:
        item = self._store.get(symbol)
        if not item:
            return True
        _, ts = item
        return time.time() - ts > self.ttl_seconds
