import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StockDataReader:
    """Minimal shared memory reader used by clients.

    This stub mirrors the error encountered by the client when the shared
    memory name or layout is not provided.  It allows tests to verify that
    consumers receive a clear ``ValueError`` in such cases.
    """

    def __init__(self, host: str, port: int, shm_name: Optional[str] = None, layout: Optional[Dict[str, List[Any]]] = None):
        self.host = host
        self.port = port
        self.shm_name = shm_name
        self.layout = layout
        logger.info("StockDataReader configured host=%s port=%s shm_name=%s", host, port, shm_name)

    def get_stock(self, ticker: str) -> List[Any]:
        """Return historical data for *ticker*.

        Raises
        ------
        ValueError
            If either ``shm_name`` or ``layout`` was not provided at
            construction time, mirroring the client's failure mode.
        KeyError
            If the ticker is absent from the layout mapping.
        """
        if not self.shm_name or self.layout is None:
            raise ValueError("Shared memory not configured")
        return self.layout[ticker]
