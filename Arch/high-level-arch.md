# High-Level Architecture

## Overview

The data manager maintains per-ticker history in shared memory and a small
in-memory quote cache for the latest point-in-time price.  A global snapshot
state tracks the last update epoch and timestamp using a seqlock style scheme.

The main entry point launches an NDJSON TCP server for discovery and point
quotes:

- `list_tickers` — returns the set of tickers backed by shared memory
- `get_quote` — retrieves the latest quote from the in-memory cache with stale
  detection against the configured freshness window
- `get_snapshot_epoch` — reports the current snapshot epoch and last update
  timestamp for observability

Clients interact with the server instead of reading the shared memory directly
for point quotes, avoiding race conditions and heavy parsing.

## Shared Memory Seqlock

Shared memory entries include a header with `epoch` and `last_update_ms`.  The
writer increments the epoch before and after updating an entry, leaving an even
value when the data is stable.  Readers verify the epoch is unchanged and even
before consuming a snapshot, ensuring they never observe torn writes.

## Data Flow

1. The data manager downloads new bars and updates shared memory entries.
2. The in-memory quote cache is refreshed with the most recent bar for each
   ticker.
3. The snapshot state is updated with the current epoch and timestamp.
4. `main.py` starts the NDJSON server, serving client requests using only the
   quote cache and snapshot state for O(1) lookups.

This separation keeps historical data in shared memory while enabling fast,
thread-safe quote retrieval over the network.

## Lightweight Integration Mode

For quick client development, the data manager exposes a hardcoded flag that
skips the full data download and instead seeds the system with randomly
generated quotes for a small subset of tickers.  This mode keeps the network
interface identical while avoiding the cost of fetching real market data.

## Example Client

See `utils/client_example.py` for a minimal example of how to interact with
the NDJSON quote server.  Every request must include the protocol version `v`,
an `id` chosen by the client, and a `type` describing the operation.  Omitting
any of these fields will result in a `BAD_REQUEST` error such as "Missing
required fields".

## Client-Side Smoke Tests

For validating a deployment, a set of client-side smoke tests lives in
`utils/smoke_tests`.  The script exercises all public endpoints and common error
paths against a running server to ensure the full request/response cycle works
as expected:

- `list_tickers`
- `get_quote`
- `get_snapshot_epoch`
- `get_quote` with an unknown ticker (expecting `NOT_FOUND`)
- a request missing required fields (expecting `BAD_REQUEST`)

Run the tests with::

    python utils/smoke_tests/run_smoke_tests.py

## Protocol and Logging Details

The TCP service speaks [NDJSON](https://ndjson.org/): each line is a single
JSON document encoded in UTF-8 and terminated by ``\n``.  The server rejects
lines larger than ``max_line_bytes`` (default 64 KiB) or malformed JSON with a
``BAD_REQUEST`` error.  Successful responses include ``type":"response`` and an
``op`` matching the request, while errors return ``type":"error`` and an
``error`` object containing a ``code`` and human readable ``message``.

Error codes:

- ``BAD_REQUEST`` – malformed JSON or missing required fields
- ``NOT_FOUND`` – unknown ticker symbol
- ``INTERNAL`` – unexpected server failure

For deep debugging, the server logs every decoded request and sent response
along with the client's socket address.  When an error occurs, the log entry
also prints the offending request to simplify troubleshooting.

The example client configures ``logging`` so that both outbound requests and
incoming responses are written to stdout, mirroring what the server reports.
