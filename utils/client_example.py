"""Example client for NDJSON quote server.

This script demonstrates how to interact with the NDJSON TCP quote
server provided by the data manager.  All outbound requests and inbound
responses are logged so they can be cross referenced with the server
logs for deep debugging.

Each request must include three fields:

- ``v`` – protocol version (always ``1``)
- ``id`` – client-supplied correlation identifier
- ``type`` – operation such as ``list_tickers`` or ``get_quote``

The server responds with ``type":"response`` and an ``op`` matching the
request or ``type":"error`` with an ``error`` object containing
``code`` and ``message``.  ``BAD_REQUEST`` is returned if any required
field is missing.

Running this module as a script will print the list of tickers, the
current quote for the first ticker and the snapshot epoch metadata.
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


def get_snapshot_epoch() -> Dict[str, Any]:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_snapshot_epoch"}
    resp = _send(req)
    return resp.get("data", {})


if __name__ == "__main__":  # pragma: no cover - example usage
    logging.basicConfig(level=logging.INFO)
    tickers = list_tickers()
    print("Tickers:", tickers)
    if tickers:
        quote = get_quote(tickers[0])
        print("Quote for", tickers[0], ":", quote)
    snapshot = get_snapshot_epoch()
    print("Snapshot state:", snapshot)
