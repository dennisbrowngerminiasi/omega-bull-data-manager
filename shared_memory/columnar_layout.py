"""Helpers for the columnar shared memory layout.

This module defines a fixed columnar layout for per-ticker OHLCV data stored
in a shared memory region.  Each ticker owns a small header followed by six
contiguous columns (timestamp, open, high, low, close, volume).  Arrays are laid
out in column-major form to enable zero-copy NumPy ``frombuffer`` views.

The layout is intentionally simple: callers pre-compute an ``offset`` and
``capacity`` for each ticker and then use :func:`compute_layout` to derive the
byte offsets for each column within the shared memory buffer.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
# ``<QQQI`` packs ``write_idx`` (u64), ``capacity`` (u64), ``last_ts`` (u64) and a
# ``seqlock`` (u32).  The struct is little-endian with no padding.
HEADER_STRUCT = struct.Struct("<QQQI")
HEADER_SIZE = HEADER_STRUCT.size


@dataclass
class TickerLayout:
    """Offsets for a single ticker within the shared memory region."""

    offset: int
    capacity: int
    ts_off: int
    o_off: int
    h_off: int
    l_off: int
    c_off: int
    v_off: int
    end: int


def compute_layout(base_off: int, capacity: int) -> TickerLayout:
    """Return a :class:`TickerLayout` describing memory offsets.

    The layout is ``HEADER`` followed by six typed columns.  Columns are stored
    contiguously and do not include any padding between them.
    """

    ts_off = base_off + HEADER_SIZE
    o_off = ts_off + 8 * capacity
    h_off = o_off + 4 * capacity
    l_off = h_off + 4 * capacity
    c_off = l_off + 4 * capacity
    v_off = c_off + 4 * capacity
    end = v_off + 8 * capacity
    return TickerLayout(
        offset=base_off,
        capacity=capacity,
        ts_off=ts_off,
        o_off=o_off,
        h_off=h_off,
        l_off=l_off,
        c_off=c_off,
        v_off=v_off,
        end=end,
    )


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

def read_header(buf: memoryview, tl: TickerLayout) -> Dict[str, int]:
    """Read the header for ``tl`` from ``buf``.

    Returns a dictionary containing ``write_idx``, ``capacity``, ``last_ts`` and
    ``seqlock``.
    """

    data = buf[tl.offset : tl.offset + HEADER_SIZE]
    write_idx, capacity, last_ts, seqlock = HEADER_STRUCT.unpack(data)
    return {
        "write_idx": write_idx,
        "capacity": capacity,
        "last_ts": last_ts,
        "seqlock": seqlock,
    }


def write_header(
    buf: memoryview,
    tl: TickerLayout,
    write_idx: int,
    capacity: int,
    last_ts: int,
    seqlock: int,
) -> None:
    """Write the header for ``tl`` into ``buf``."""

    buf[tl.offset : tl.offset + HEADER_SIZE] = HEADER_STRUCT.pack(
        write_idx, capacity, last_ts, seqlock
    )


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------

def column_views(buf: memoryview, tl: TickerLayout) -> Tuple[np.ndarray, ...]:
    """Return NumPy views for all six columns of ``tl``.

    The returned arrays alias the underlying shared memory; modifying them will
    mutate the shared region.
    """

    mv = memoryview(buf)
    cap = tl.capacity
    ts = np.frombuffer(mv, dtype=np.int64, count=cap, offset=tl.ts_off)
    o = np.frombuffer(mv, dtype=np.float32, count=cap, offset=tl.o_off)
    h = np.frombuffer(mv, dtype=np.float32, count=cap, offset=tl.h_off)
    l = np.frombuffer(mv, dtype=np.float32, count=cap, offset=tl.l_off)
    c = np.frombuffer(mv, dtype=np.float32, count=cap, offset=tl.c_off)
    v = np.frombuffer(mv, dtype=np.int64, count=cap, offset=tl.v_off)
    return ts, o, h, l, c, v


def ring_slice(arr: np.ndarray, start: int, end: int, capacity: int) -> np.ndarray:
    """Return a slice from ``start`` to ``end`` in a ring buffer.

    ``start`` and ``end`` are interpreted modulo ``capacity``.  The result is a
    view (or copy when wrapping occurs) in logical order from ``start`` up to but
    not including ``end``.
    """

    start %= capacity
    end %= capacity
    if start < end:
        return arr[start:end]
    if start == end:
        # full buffer
        return np.concatenate((arr[start:], arr[:start]))
    return np.concatenate((arr[start:], arr[:end]))
