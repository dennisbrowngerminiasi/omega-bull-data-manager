import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from shared_memory.columnar_writer import ColumnarWriter
from shared_memory.columnar_reader import ColumnarReader
from shared_memory.columnar_layout import compute_layout


def _build(name: str, capacity: int):
    index = {"TEST": {"offset": 0, "capacity": capacity}}
    layout = compute_layout(0, capacity)
    size = layout.end
    writer = ColumnarWriter(name, size, index)
    reader = ColumnarReader(name, index)
    return writer, reader


def test_view_last_n_and_since():
    writer, reader = _build("shm_test", 5)
    try:
        for i in range(7):
            writer.append("TEST", i, float(i), float(i), float(i), float(i), i * 10)

        ts, o, h, l, c, v = reader.view_last_n("TEST", 3)
        assert ts.tolist() == [4, 5, 6]
        assert o.tolist() == [4.0, 5.0, 6.0]
        assert v.tolist() == [40, 50, 60]

        ts2, *_ = reader.view_since("TEST", 3)
        assert ts2.tolist() == [4, 5, 6]
    finally:
        reader.close()
        writer.close()
        writer.unlink()
