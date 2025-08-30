"""Simple columnar shared-memory writer."""

from __future__ import annotations

from multiprocessing import shared_memory
from typing import Dict, Tuple

from .columnar_layout import (
    TickerLayout,
    column_views,
    compute_layout,
    read_header,
    write_header,
)


class ColumnarWriter:
    """Append-only writer for the columnar shared memory region."""

    def __init__(self, shm_name: str, size: int, index: Dict[str, Dict[str, int]]):
        self.shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size)
        self.buf = self.shm.buf
        self.layouts: Dict[str, TickerLayout] = {}
        for ticker, meta in index.items():
            layout = compute_layout(meta["offset"], meta["capacity"])
            self.layouts[ticker] = layout
            write_header(self.buf, layout, 0, layout.capacity, 0, 0)

    # ------------------------------------------------------------------
    def append(
        self,
        ticker: str,
        ts: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: int,
    ) -> Tuple[int, int]:
        """Append a row and return ``(write_idx, last_ts)`` after the write."""

        tl = self.layouts[ticker]
        header = read_header(self.buf, tl)
        wi = header["write_idx"]
        cap = header["capacity"]
        seqlock = header["seqlock"] + 1
        write_header(self.buf, tl, wi, cap, header["last_ts"], seqlock)

        ts_col, o_col, h_col, l_col, c_col, v_col = column_views(self.buf, tl)
        ts_col[wi] = ts
        o_col[wi] = o
        h_col[wi] = h
        l_col[wi] = l
        c_col[wi] = c
        v_col[wi] = v

        wi = (wi + 1) % cap
        seqlock += 1
        write_header(self.buf, tl, wi, cap, ts, seqlock)
        return wi, ts

    # ------------------------------------------------------------------
    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass
