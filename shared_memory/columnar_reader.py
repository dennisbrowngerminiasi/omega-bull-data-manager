"""Columnar shared-memory reader."""

from __future__ import annotations

from multiprocessing import shared_memory
from typing import Dict, Tuple

import numpy as np

from .columnar_layout import (
    TickerLayout,
    column_views,
    compute_layout,
    read_header,
    ring_slice,
)


class ColumnarReader:
    """Read-only view of the columnar shared memory region."""

    def __init__(self, shm_name: str, index: Dict[str, Dict[str, int]]):
        self.shm = shared_memory.SharedMemory(name=shm_name)
        self.buf = self.shm.buf
        self.layouts: Dict[str, TickerLayout] = {
            t: compute_layout(m["offset"], m["capacity"]) for t, m in index.items()
        }

    # ------------------------------------------------------------------
    def _read_cols(self, ticker: str) -> Tuple[np.ndarray, ...]:
        tl = self.layouts[ticker]
        header = read_header(self.buf, tl)
        cols = column_views(self.buf, tl)
        header2 = read_header(self.buf, tl)
        if header2["seqlock"] % 2 or header2 != header:
            # retry once
            cols = column_views(self.buf, tl)
            header2 = read_header(self.buf, tl)
        self._last_header = header2
        return cols

    # ------------------------------------------------------------------
    def view_last_n(self, ticker: str, n: int) -> Tuple[np.ndarray, ...]:
        cols = self._read_cols(ticker)
        header = self._last_header
        cap = header["capacity"]
        n = min(n, cap)
        end = header["write_idx"]
        start = (end - n) % cap
        return tuple(ring_slice(col, start, end, cap) for col in cols)

    def view_since(self, ticker: str, ts_threshold: int) -> Tuple[np.ndarray, ...]:
        tl = self.layouts[ticker]
        header = read_header(self.buf, tl)
        cap = header["capacity"]
        cols = self.view_last_n(ticker, cap)
        ts = cols[0]
        mask = ts > ts_threshold
        return tuple(col[mask] for col in cols)

    # ------------------------------------------------------------------
    def close(self) -> None:
        self.shm.close()
