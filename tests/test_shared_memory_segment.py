import pytest
from multiprocessing import shared_memory

from main import _ensure_shared_memory


def test_ensure_shared_memory_recreates_existing():
    name = "test_shm_segment"
    size = 1024

    # simulate leftover shared-memory segment from previous crash
    leftover = shared_memory.SharedMemory(name=name, create=True, size=size)
    leftover.close()  # intentionally do not unlink

    shm = _ensure_shared_memory(name, size)
    try:
        assert shm.name == name
        assert shm.size == size
    finally:
        shm.close()
        shm.unlink()
