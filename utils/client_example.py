"""Example client for NDJSON quote server.

This script demonstrates how to interact with the NDJSON TCP quote
server provided by the data manager.  It shows how to list available
tickers and request a quote for a specific ticker.

Each request must include:
- ``v``: protocol version (1)
- ``id``: client-supplied correlation identifier
- ``type``: request operation such as ``list_tickers`` or ``get_quote``

Running this module as a script will print the list of tickers and the
quote for the first ticker in the list.
"""

from __future__ import annotations

import json
import logging
import socket
import uuid
from typing import Any, Dict, List

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


if __name__ == "__main__":  # pragma: no cover - example usage
    logging.basicConfig(level=logging.INFO)
    tickers = list_tickers()
    print("Tickers:", tickers)
    if tickers:
        quote = get_quote(tickers[0])
        print("Quote for", tickers[0], ":", quote)
