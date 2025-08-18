# Columnar Shared Memory and Notifications

This document sketches the new columnar data path used by the data manager.
Instead of serialising every update as JSON, each ticker owns a fixed-capacity
ring buffer inside a shared-memory segment.  Columns are stored contiguously and
read by clients using zero‑copy NumPy views.

## Layout

Each ticker starts with a small header guarded by a seqlock followed by six
columns: timestamp, open, high, low, close and volume.  Offsets are calculated
with `compute_layout` so that writers and readers agree on the exact byte
positions.  Writers bump the `seqlock` to an odd value, write the new row, then
bump it again to publish a stable even snapshot.

## Reader API

`ColumnarReader` exposes two helpers:

- `view_last_n(ticker, n)` – return NumPy views over the most recent `n` rows
  without copying.
- `view_since(ticker, ts)` – return all rows newer than a given timestamp.

Both helpers slice the underlying ring buffer in logical order so callers receive
chronologically sorted arrays.

## Writer API

`ColumnarWriter.append` records a single OHLCV row.  The method returns the new
write index and last timestamp so higher layers can relay change notifications to
subscribers.

## Notifications

The full system design includes a Unix Domain Socket broadcast channel where the
writer emits tick messages.  Clients subscribe via the control plane and only
wake when relevant data arrives, removing the need for polling.  The initial
implementation in this repository provides the columnar reader/writer while
leaving the networking pieces for future work.
