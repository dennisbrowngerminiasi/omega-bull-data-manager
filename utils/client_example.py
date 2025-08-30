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

``get_shm_name``
    Discover the name of the shared-memory segment used for historical
    bars.  Clients need this value to attach directly for history reads.  The
    server responds with an error if no shared-memory region is configured.

``StockDataReader.get_stock``
    (client side) Read historical bars directly from the shared memory
    region using a seqlock style loop that verifies the per‑ticker epoch
    before and after loading the JSON payload.  The example below shows
    how a client would instantiate the reader once the shared-memory name
    is discovered.

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

1. Print the shared-memory segment name.
2. Print the list of available tickers.
3. Retrieve and print the latest quote for the first ticker.
4. Show the snapshot epoch metadata.
5. Attempt to read historical bars for the first ticker using
   :class:`StockDataReader` and a lower-level helper that explicitly
   demonstrates the seqlock epoch dance.
"""

from __future__ import annotations

import json
import logging
import socket
import uuid
from typing import Any, Dict, List
from multiprocessing import shared_memory

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


def get_fundamentals(ticker: str, fresh: bool = False) -> Dict[str, Any]:
    """Fetch cached fundamentals for ``ticker``.

    If ``fresh`` is True the server is asked to refresh the data in the
    background but the response still returns any cached value immediately.
    """

    req = {
        "v": 1,
        "id": str(uuid.uuid4()),
        "type": "get_fundamentals",
        "ticker": ticker,
    }
    if fresh:
        req["fresh"] = True
    resp = _send(req)
    return resp.get("data", {})


def get_snapshot_epoch() -> Dict[str, Any]:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_snapshot_epoch"}
    resp = _send(req)
    return resp.get("data", {})


def get_shm_name() -> str:
    """Return the shared-memory segment name advertised by the server."""
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_shm_name"}
    resp = _send(req)
    return resp.get("data", {}).get("shm_name", "")


def get_history(reader: StockDataReader, ticker: str) -> List[Any]:
    """Return historical bars for ``ticker`` using ``reader``.

    The reader must be configured with a valid shared-memory segment name.
    Any configuration problems are logged so callers can diagnose issues
    such as the segment being too small or absent.
    """

    try:
        entry = reader.get_stock(ticker)
        points = entry.get("df", []) if isinstance(entry, dict) else entry
        logger.info("received %d history points", len(points))
        return points
    except Exception as exc:  # broad to surface config issues to user
        logger.error("history read failed: %s", exc)
        return []


def read_history_with_epoch(shm_name: str, ticker: str, max_retries: int = 6) -> List[Any]:
    """Manually read ``ticker`` using the seqlock protocol.

    This function demonstrates the low-level algorithm that
    :class:`StockDataReader` uses: the epoch is captured before and after
    reading the JSON payload to ensure the writer was not in the middle of
    an update.  The function retries a few times if the epoch is odd or
    changes between reads.
    """

    shm = shared_memory.SharedMemory(name=shm_name)
    try:
        for attempt in range(max_retries):
            raw = bytes(shm.buf).rstrip(b"\x00")
            if not raw:
                return []
            data = json.loads(raw.decode("utf-8"))
            entry = data.get(ticker)
            if entry is None:
                raise KeyError(ticker)

            e1 = entry.get("header", {}).get("epoch")
            if e1 is None or e1 % 2:
                logger.debug("writer in progress e1=%s attempt=%d", e1, attempt)
                continue

            payload = entry.get("data")
            points = payload.get("df", []) if isinstance(payload, dict) else []

            raw2 = bytes(shm.buf).rstrip(b"\x00")
            data2 = json.loads(raw2.decode("utf-8"))
            e2 = data2.get(ticker, {}).get("header", {}).get("epoch")

            if e1 == e2 and e2 is not None and e2 % 2 == 0:
                logger.info("stable epoch %s for %s", e2, ticker)
                return points

            logger.debug("retry %d for %s: e1=%s e2=%s", attempt, ticker, e1, e2)

        raise RuntimeError("Could not obtain a stable snapshot after retries")
    finally:
        shm.close()


if __name__ == "__main__":  # pragma: no cover - example usage
    logging.basicConfig(level=logging.INFO)
    shm = get_shm_name()
    print("Shared memory name:", shm)
    tickers = list_tickers()
    print("Tickers:", tickers)

    if tickers:
        first = tickers[0]
        quote = get_quote(first)
        print("Quote for", first, ":", quote)

        # Demonstrate shared-memory history access.  In a production setup the
        # data manager advertises the ``shm_name`` which is passed to
        # ``StockDataReader``.
        reader = StockDataReader(HOST, PORT, shm_name=shm)
        history = get_history(reader, first)
        if history:
            print("First history point via reader:", history[0])

        # Also show the explicit seqlock algorithm for educational purposes.
        try:
            manual = read_history_with_epoch(shm, first)
            if manual:
                print("First history point via seqlock:", manual[0])
        except Exception as exc:
            logger.error("manual seqlock read failed: %s", exc)

    snapshot = get_snapshot_epoch()
    print("Snapshot state:", snapshot)
