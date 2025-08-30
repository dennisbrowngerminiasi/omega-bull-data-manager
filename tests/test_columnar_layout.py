import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from shared_memory.columnar_layout import (
    compute_layout,
    read_header,
    write_header,
    column_views,
    ring_slice,
)


def test_layout_and_header_helpers():
    tl = compute_layout(0, 4)
    buf = bytearray(tl.end)
    mv = memoryview(buf)
    write_header(mv, tl, 1, tl.capacity, 123, 2)
    header = read_header(mv, tl)
    assert header == {
        "write_idx": 1,
        "capacity": 4,
        "last_ts": 123,
        "seqlock": 2,
    }

    ts, o, h, l, c, v = column_views(mv, tl)
    ts[:] = np.arange(4, dtype=np.int64)
    o[:] = np.arange(4, dtype=np.float32) * 0.1
    assert ts.tolist() == [0, 1, 2, 3]
    assert float(o[3]) == np.float32(0.3)


def test_ring_slice():
    arr = np.array([0, 1, 2, 3, 4])
    assert ring_slice(arr, 3, 1, 5).tolist() == [3, 4, 0]
    assert ring_slice(arr, 0, 0, 5).tolist() == [0, 1, 2, 3, 4]
