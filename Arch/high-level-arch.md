# High-Level Architecture

## Overview

The data manager maintains per-ticker history in shared memory and a small
in-memory quote cache for the latest point-in-time price.  A global snapshot
state tracks the last update epoch and timestamp using a seqlock style scheme.

An NDJSON TCP server exposes discovery and point quote endpoints:

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
4. The NDJSON server serves client requests using only the quote cache and
   snapshot state for O(1) lookups.

This separation keeps historical data in shared memory while enabling fast,
thread-safe quote retrieval over the network.
