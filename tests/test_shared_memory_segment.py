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


def test_ensure_shared_memory_retries_until_available(monkeypatch):
    name = "test_shm_retry"
    size = 1024

    # Create a leftover segment to trigger the recreation path.
    leftover = shared_memory.SharedMemory(name=name, create=True, size=size)
    leftover.close()  # do not unlink so the segment persists

    real_shared_memory = shared_memory.SharedMemory
    calls = {"create": 0}

    def flaky_shared_memory(*args, **kwargs):
        create = kwargs.get("create", False)
        if create:
            calls["create"] += 1
            # Fail the first two creation attempts to exercise the retry loop.
            if calls["create"] < 3:
                raise FileExistsError
        return real_shared_memory(*args, **kwargs)

    monkeypatch.setattr(shared_memory, "SharedMemory", flaky_shared_memory)

    shm = _ensure_shared_memory(name, size)
    try:
        # Ensure the retry loop attempted creation multiple times before succeeding.
        assert calls["create"] == 3
    finally:
        shm.close()
        shm.unlink()
