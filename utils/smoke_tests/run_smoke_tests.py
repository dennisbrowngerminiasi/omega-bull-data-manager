"""Client-side smoke tests for the NDJSON quote server.

These tests exercise the public NDJSON endpoints using the client example
helpers.  A running quote server is required; by default the tests connect to
127.0.0.1:12345.  Each test prints its result and raises an AssertionError on
failure.

Usage:
    python utils/smoke_tests/run_smoke_tests.py
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

from utils import client_example as client


def _assert(condition: bool, message: str) -> None:
    """Raise an AssertionError with ``message`` if ``condition`` is False."""
    if not condition:
        raise AssertionError(message)


def test_list_tickers() -> None:
    tickers = client.list_tickers()
    _assert(isinstance(tickers, list) and tickers, "list_tickers returned no data")
    print("list_tickers ->", tickers)

    # basic structural checks
    for t in tickers:
        _assert(isinstance(t, str) and t, f"invalid ticker: {t!r}")


def test_get_quote() -> str:
    tickers = client.list_tickers()
    _assert(tickers, "no tickers available for get_quote")
    ticker = tickers[0]
    quote = client.get_quote(ticker)
    _assert(quote.get("ticker") == ticker, f"quote ticker mismatch: {quote}")
    _assert("price" in quote and "volume" in quote, "quote missing fields")
    print(f"get_quote({ticker}) ->", quote)
    return ticker


def test_get_snapshot_epoch() -> None:
    snap = client.get_snapshot_epoch()
    _assert("epoch" in snap and "last_update_ms" in snap, "snapshot missing fields")
    print("get_snapshot_epoch ->", snap)


def test_not_found() -> None:
    req = {"v": 1, "id": str(uuid.uuid4()), "type": "get_quote", "ticker": "__MISSING__"}
    resp: Dict[str, Any] = client._send(req)  # type: ignore[attr-defined]
    _assert(resp.get("type") == "error" and resp.get("error", {}).get("code") == "NOT_FOUND",
            f"expected NOT_FOUND, got {resp}")
    print("get_quote unknown ticker ->", resp["error"])


def test_bad_request() -> None:
    resp: Dict[str, Any] = client._send({"v": 1})  # type: ignore[attr-defined]
    err = resp.get("error", {})
    _assert(resp.get("type") == "error" and err.get("code") == "BAD_REQUEST",
            f"expected BAD_REQUEST, got {resp}")
    _assert("id" in err.get("message", "") and "type" in err.get("message", ""),
            f"error message missing details: {resp}")
    print("missing required fields ->", err)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(f"Running smoke tests against {client.HOST}:{client.PORT}")
    test_list_tickers()
    ticker = test_get_quote()
    test_get_snapshot_epoch()
    test_not_found()
    test_bad_request()
    print("All smoke tests passed for ticker", ticker)


if __name__ == "__main__":
    main()
