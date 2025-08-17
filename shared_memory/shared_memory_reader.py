import json
import logging
from typing import Any, Dict, List, Optional
from multiprocessing import shared_memory

logger = logging.getLogger(__name__)


class StockDataReader:
    """Read historical stock data from a shared-memory segment.

    The reader understands the JSON layout produced by
    :class:`SharedMemoryManager`.  For each ticker the segment contains a
    dictionary with a seqlock style header and the serialized data.  The reader
    retries a few times if it observes an odd epoch or if the JSON payload is
    being updated while reading.
    """

    def __init__(
        self,
        host: str,
        port: int,
        shm_name: Optional[str] = None,
        layout: Optional[Dict[str, List[Any]]] = None,
        max_retries: int = 6,
    ) -> None:
        self.host = host
        self.port = port
        self.shm_name = shm_name
        self.layout = layout
        self.max_retries = max_retries
        self._shm: Optional[shared_memory.SharedMemory] = None

        if shm_name is not None:
            # Attach to the advertised shared-memory segment so history reads can
            # be served directly from the writer's dictionary.
            self._shm = shared_memory.SharedMemory(name=shm_name)
            logger.info(
                "StockDataReader opened shared memory %s (%d bytes)",
                shm_name,
                self._shm.size,
            )
        else:
            logger.info(
                "StockDataReader configured without shared memory; layout=%s",
                bool(layout),
            )

    # ------------------------------------------------------------------
    def close(self) -> None:
        """Detach from the shared-memory segment if one is open."""
        if self._shm is not None:
            self._shm.close()
            self._shm = None

    # ------------------------------------------------------------------
    def _load_dict(self) -> Dict[str, Any]:
        if self._shm is None:
            return {}
        raw = bytes(self._shm.buf).rstrip(b"\x00")
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------------
    def list_tickers(self) -> List[str]:
        """Return the set of tickers available in shared memory."""
        if self.layout is not None:
            keys = list(self.layout.keys())
            logger.info("Available tickers from provided layout: %s", keys)
            return keys
        if self._shm is None:
            raise ValueError("Shared memory not configured")
        data = self._load_dict()
        keys = list(data.keys())
        logger.info("Available tickers: %s", keys)
        return keys

    # ------------------------------------------------------------------
    def get_stock(self, ticker: str) -> Any:
        """Return historical data for ``ticker``.

        When ``layout`` is provided the data is returned from that mapping,
        mirroring the configuration-only reader used in the smoke tests.  When
        backed by real shared memory, the reader retries up to ``max_retries``
        times until it observes a stable seqlock epoch.
        """
        if self.layout is not None:
            if ticker not in self.layout:
                raise KeyError(ticker)
            return self.layout[ticker]

        if self._shm is None:
            raise ValueError("Shared memory not configured")

        for attempt in range(self.max_retries):
            try:
                data = self._load_dict()
            except json.JSONDecodeError as exc:  # partial write
                logger.debug("JSON decode error on attempt %d: %s", attempt, exc)
                continue

            entry = data.get(ticker)
            if entry is None:
                raise KeyError(ticker)

            e1 = entry.get("header", {}).get("epoch")
            if e1 is None or e1 % 2:
                logger.debug("Epoch %s invalid on attempt %d", e1, attempt)
                continue

            payload = entry.get("data")
            try:
                data2 = self._load_dict()
            except json.JSONDecodeError as exc:  # writer in progress
                logger.debug("JSON decode error on reread %d: %s", attempt, exc)
                continue

            e2 = data2.get(ticker, {}).get("header", {}).get("epoch")
            if e1 == e2 and e2 is not None and e2 % 2 == 0:
                return payload
            logger.debug("Retry %d for %s: e1=%s e2=%s", attempt, ticker, e1, e2)

        raise RuntimeError("Could not obtain a stable snapshot after retries")
