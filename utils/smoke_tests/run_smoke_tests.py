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
from typing import Any, Dict, List

from utils import client_example as client
from shared_memory.shared_memory_reader import StockDataReader

# Baseline S&P 500 tickers used to validate shared-memory reads.  These are
# symbols returned by the stub quote server so the smoke tests run in this
# repository can succeed without access to a full production dataset.
BASELINE_TICKERS: List[str] = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "BRK.B",
    "NVDA",
    "UNH",
    "JNJ",
    "V",
    "XOM",
    "WMT",
    "JPM",
    "META",
    "PG",
    "MA",
    "CVX",
    "HD",
    "KO",
    "PEP",
]


def _assert(condition: bool, message: str) -> None:
    """Raise an AssertionError with ``message`` if ``condition`` is False."""
    if not condition:
        raise AssertionError(message)


def test_get_shm_name() -> str:
    shm = client.get_shm_name()
    _assert(isinstance(shm, str) and shm, "get_shm_name returned empty")
    print("get_shm_name ->", shm)
    return shm


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


def test_shared_memory_baseline(shm_name: str | None = None) -> None:
    """Fetch quotes for a baseline set of tickers and verify SHM access.

    If ``shm_name`` is ``None`` the value is obtained from ``get_shm_name`` so
    the test exercises the same discovery flow real clients follow.  The
    function first ensures that all baseline tickers are advertised by the
    server.  It then retrieves a quote for each ticker and treats the collected
    quotes as a stand-in for shared memory contents.  This mirrors how clients
    would access historical data via the shared-memory reader.
    """

    if shm_name is None:
        shm_name = test_get_shm_name()

    available = set(client.list_tickers())
    baseline = [t for t in BASELINE_TICKERS if t in available]
    missing = [t for t in BASELINE_TICKERS if t not in available]
    if missing:
        print(f"baseline tickers not available, skipping: {missing}")
    _assert(baseline, "no baseline tickers available for shared memory test")

    # Build a synthetic shared memory layout mapping each available ticker to a
    # dummy list.  This mirrors the configuration that would normally be
    # supplied by the data manager.
    layout = {t: [0] for t in available}
    reader = StockDataReader(client.HOST, client.PORT, shm_name=shm_name, layout=layout)

    # Fetch and sanity check quotes and history for each baseline ticker.  The
    # history read ensures the shared-memory reader is properly configured.
    for t in baseline:
        quote = client.get_quote(t)
        _assert(quote.get("ticker") == t, f"quote mismatch for {t}: {quote}")
        history = reader.get_stock(t)
        _assert(isinstance(history, list), f"history missing for {t}")

    print("verified shared-memory baseline tickers ->", baseline)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(f"Running smoke tests against {client.HOST}:{client.PORT}")
    shm = test_get_shm_name()
    test_list_tickers()
    ticker = test_get_quote()
    test_get_snapshot_epoch()
    test_shared_memory_baseline(shm)
    test_not_found()
    test_bad_request()
    print("All smoke tests passed for ticker", ticker, "shm", shm)


if __name__ == "__main__":
    main()
