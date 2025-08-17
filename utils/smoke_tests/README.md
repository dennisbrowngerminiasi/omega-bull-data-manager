# NDJSON Quote Server Smoke Tests

This directory contains a small battery of client-side smoke tests for the
NDJSON quote server.  They verify that all public endpoints respond correctly
and that common error paths return the expected codes.  The tests fetch the
shared-memory name from the server via ``get_shm_name`` and instantiate a
``StockDataReader`` with that name and a synthetic layout derived from the
server's advertised tickers so that the shared-memory access path is exercised
end to end.

## Usage

1. Ensure the quote server is running and accessible at the host/port defined in
   `utils/client_example.py` (defaults to `127.0.0.1:12345`).
2. Run the smoke tests:

```bash
python utils/smoke_tests/run_smoke_tests.py
```

The script exercises the following operations:

- `list_tickers`
- `get_quote` (success and unknown ticker)
- `get_snapshot_epoch`
- Verifies that a baseline set of popular S&P 500 tickers (e.g. AAPL, MSFT,
  AMZN) are present and retrievable
- Requests with missing required fields (expecting `BAD_REQUEST`)

Any assertion failures will raise an exception and halt the script.
