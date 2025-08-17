"""Reference client for the NDJSON quote server.

This module demonstrates the full set of request/response operations
supported by the NDJSON TCP service:

``list_tickers``
    Discover the tickers currently backed by shared memory.

``get_quote``
    Fetch a point-in-time quote from the in-memory cache.  The server
    replies with pricing fields such as ``price`` and ``volume`` along
    with metadata like ``currency`` and ``stale``.

``get_snapshot_epoch``
    Inspect the global snapshot seqlock state to understand when the
    shared memory was last updated.

``StockDataReader.get_stock``
    (client side) Read historical bars directly from the shared memory
    region.  This requires the shared memory name and layout mapping used
    by the data manager.  The example below shows how a client would
    instantiate the reader once this information is obtained out of band.

Every request sent to the server **must** include three fields:

``v``
    Protocol version (always ``1``).

``id``
    Client supplied correlation identifier used to match requests with
    responses.

``type``
    Operation such as ``list_tickers`` or ``get_quote``.  Missing any of
    the above fields will yield a ``BAD_REQUEST`` error with the list of
    missing names.

When executed as a script this module will:

1. Print the list of available tickers.
2. Retrieve and print the latest quote for the first ticker.
3. Show the snapshot epoch metadata.
4. Attempt to read historical bars for the first ticker using
   :class:`StockDataReader`.  If the shared memory configuration is not
   supplied, a helpful error is logged explaining what is missing.
"""

from __future__ import annotations

import json
import logging
import socket
import uuid
from typing import Any, Dict, List

from shared_memory.shared_memory_reader import StockDataReader

HOST = "127.0.0.1"
PORT = 12345


logger = logging.getLogger(__name__)


def _send(request: Dict[str, Any]) -> Dict[str, Any]:
    """Send a request and return the parsed JSON response."""
    logger.info("sending request: %s", request)
    line = json.dumps(request).encode("utf-8") + b"\n"
    with socket.create_connection((HOST, PORT)) as sock:
        sock.sendall(line)
        response_line = sock.makefile("r").readline()
    logger.info("received response: %s", response_line.strip())
    return json.loads(response_line)


def list_tickers() -> List[str]:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "list_tickers"}
    resp = _send(req)
    return resp.get("data", [])


def get_quote(ticker: str) -> Dict[str, Any]:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_quote", "ticker": ticker}
    resp = _send(req)
    return resp.get("data", {})


def get_snapshot_epoch() -> Dict[str, Any]:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_snapshot_epoch"}
    resp = _send(req)
    return resp.get("data", {})


def get_history(reader: StockDataReader, ticker: str) -> List[Any]:
    """Return historical bars for ``ticker`` using ``reader``.

    If the reader was not configured with ``shm_name`` and ``layout`` a
    ``ValueError`` will be raised and logged.
    """

    try:
        history = reader.get_stock(ticker)
        logger.info("received %d history points", len(history))
        return history
    except Exception as exc:  # broad to surface config issues to user
        logger.error("history read failed: %s", exc)
        return []


if __name__ == "__main__":  # pragma: no cover - example usage
    logging.basicConfig(level=logging.INFO)
    tickers = list_tickers()
    print("Tickers:", tickers)

    if tickers:
        first = tickers[0]
        quote = get_quote(first)
        print("Quote for", first, ":", quote)

        # Demonstrate shared-memory history access.  In a production setup
        # ``shm_name`` and ``layout`` would be supplied by the data manager.
        reader = StockDataReader(HOST, PORT, shm_name=None, layout=None)
        history = get_history(reader, first)
        if history:
            print("First history point:", history[0])

    snapshot = get_snapshot_epoch()
    print("Snapshot state:", snapshot)
