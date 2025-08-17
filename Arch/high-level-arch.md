# High-Level Architecture

## Overview

The data manager maintains per-ticker history in shared memory and a small
in-memory quote cache for the latest point-in-time price.  A global snapshot
state tracks the last update epoch and timestamp using a seqlock style scheme.

The main entry point launches an NDJSON TCP server for discovery and point
quotes.  To keep client integrations simple, it also creates a small operating
system shared-memory segment named `"shm0"` and seeds the shared-memory manager
with that name so clients can attach to the historical data region via
`get_shm_name`:

- `get_shm_name` — reveals the name of the shared-memory segment used for
  historical bars. If shared memory is not configured, the server responds with
  a `NOT_FOUND` error.
- `list_tickers` — returns the set of tickers backed by shared memory
- `get_quote` — retrieves the latest quote from the in-memory cache with stale
  detection against the configured freshness window
- `get_snapshot_epoch` — reports the current snapshot epoch and last update
  timestamp for observability

Because clients must discover the shared-memory region dynamically,
`get_shm_name` is a first-class endpoint in this architecture rather than a
legacy helper; any compliant server should implement it whenever shared memory
is available. Clients interact with the server instead of reading the shared
memory directly for point quotes, avoiding race conditions and heavy parsing.

## Shared Memory Seqlock

Shared memory entries include a header with `epoch` and `last_update_ms`.  The
writer increments the epoch before and after updating an entry, leaving an even
value when the data is stable.  Readers verify the epoch is unchanged and even
before consuming a snapshot, ensuring they never observe torn writes.

### Layout and Write Protocol

Shared memory is represented by a process-safe dictionary where each key is the
stock's ticker symbol.  After each batch update the manager serializes this
dictionary into the operating system's shared-memory segment (for example
`shm0`) so external clients can map the region directly.  Each entry contains
two top-level fields:

```
{
  "header": {
    "version": 1,
    "epoch": <u64>,
    "last_update_ms": <u64>,
    "writer_pid": <u32>
  },
  "data": <serialized OHLCV history>
}
```

The data manager's `write_data` method performs the following steps:

1. Acquire a global lock and bump the global snapshot `epoch` to an **odd**
   number to signal that updates are in progress.
2. For each ticker:
   - Create or fetch its entry from the dictionary.
   - Increment the entry's `epoch` to an odd value.
   - Store the latest historical data and update `last_update_ms`.
   - Increment the `epoch` again, making it even and therefore stable.
   - Publish a condensed quote into the in-memory `quote_cache` so the TCP
     server can serve `get_quote` without touching shared memory.
3. After all tickers are processed, update the global `last_update_ms`, bump
   the global `epoch` to the next even value, and release the lock.

This seqlock pattern guarantees readers either see a fully written snapshot or
retry until one is available.

### Client Read Protocol

Clients that need historical bars may attach to the shared dictionary directly
and read using the same seqlock fields.  A minimal reader can follow this
algorithm:

```
def read_ticker(shared_dict, ticker):
    while True:
        entry = shared_dict[ticker]
        e1 = entry["header"]["epoch"]
        if e1 % 2:  # writer in progress
            continue
        data = entry["data"]
        e2 = entry["header"]["epoch"]
        if e1 == e2 and e2 % 2 == 0:
            return data  # consistent snapshot
```

The global snapshot state (`snapshot_state`) exposes the latest `epoch` and
`last_update_ms` and can be polled to detect when new data arrives.  For point
quotes and discovery, clients should prefer the NDJSON server which reads from
the in-memory `quote_cache` and avoids seqlock coordination entirely.

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

See `utils/client_example.py` and the accompanying `utils/README.md` for a
reference implementation of all client operations.  The examples show how to:

- enumerate tickers with ``list_tickers``
- discover the shared-memory segment with ``get_shm_name``
- fetch point quotes via ``get_quote``
- inspect the snapshot state using ``get_snapshot_epoch``
- read historical bars from shared memory with ``StockDataReader``

Every request sent to the TCP service must include the protocol version
`v`, an `id` chosen by the client, and a `type` describing the operation.
Omitting any of these fields yields a `BAD_REQUEST` error naming the missing
fields.

## Client-Side Smoke Tests

For validating a deployment, a set of client-side smoke tests lives in
`utils/smoke_tests`.  The script exercises all public endpoints and common error
paths against a running server to ensure the full request/response cycle works
as expected:

- `get_shm_name` (expect `NOT_FOUND` if shared memory is disabled)
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
