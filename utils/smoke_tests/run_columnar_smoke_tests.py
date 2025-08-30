"""Smoke tests for the columnar shared-memory protocol.

These tests exercise the low-level helpers, writer and reader used by the
columnar shared-memory feature.  They can be run standalone via
``python utils/smoke_tests/run_columnar_smoke_tests.py`` or through pytest.
"""

from __future__ import annotations

import numpy as np

from shared_memory.columnar_layout import (
    compute_layout,
    read_header,
    write_header,
    column_views,
    ring_slice,
)
from shared_memory.columnar_writer import ColumnarWriter
from shared_memory.columnar_reader import ColumnarReader


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_compute_layout() -> None:
    tl = compute_layout(0, 4)
    _assert(tl.capacity == 4 and tl.ts_off > 0, "compute_layout returned invalid layout")
    print("compute_layout ->", tl)


def test_header_and_views() -> None:
    tl = compute_layout(0, 2)
    buf = bytearray(tl.end)
    mv = memoryview(buf)
    write_header(mv, tl, 0, tl.capacity, 0, 0)
    header = read_header(mv, tl)
    _assert(header["capacity"] == 2, "header capacity mismatch")
    ts, o, h, l, c, v = column_views(mv, tl)
    ts[:] = [1, 2]
    o[:] = [1.0, 2.0]
    _assert(ts.tolist() == [1, 2] and float(o[1]) == 2.0, "column_views failed")
    print("header read/write and column_views ->", header)


def test_ring_slice() -> None:
    arr = np.array([0, 1, 2, 3, 4])
    sliced = ring_slice(arr, 3, 1, 5)
    _assert(sliced.tolist() == [3, 4, 0], f"ring_slice returned {sliced}")
    print("ring_slice ->", sliced.tolist())


def test_writer_and_reader() -> None:
    index = {"T": {"offset": 0, "capacity": 3}}
    layout = compute_layout(0, 3)
    writer = ColumnarWriter("col_smoke", layout.end, index)
    reader = ColumnarReader("col_smoke", index)
    try:
        for i in range(5):
            writer.append("T", i, float(i), float(i), float(i), float(i), i)
        ts, *_ = reader.view_last_n("T", 2)
        _assert(ts.tolist() == [3, 4], f"view_last_n returned {ts.tolist()}")
        ts2, *_ = reader.view_since("T", 2)
        _assert(ts2.tolist() == [3, 4], f"view_since returned {ts2.tolist()}")
        print("writer/reader last_n ->", ts.tolist())
    finally:
        # Drop references to NumPy arrays before closing shared memory.
        del ts, ts2
        reader.close()
        writer.close()
        writer.unlink()


def main() -> None:
    test_compute_layout()
    test_header_and_views()
    test_ring_slice()
    test_writer_and_reader()
    print("All columnar smoke tests passed")


if __name__ == "__main__":
    main()
