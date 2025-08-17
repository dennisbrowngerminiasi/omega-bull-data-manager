import asyncio
import logging
import time
from threading import Lock
from multiprocessing import shared_memory

from shared_memory.shared_memory_manager import SharedMemoryManager
from stock.stock_data_manager import StockDataManager
from quote_server import NDJSONServer


def _ensure_shared_memory(name: str, size: int) -> shared_memory.SharedMemory:
    """Create or replace a named shared-memory segment.

    If a segment with *name* already exists (e.g. leftover from a previous
    crash), it is unlinked before a fresh segment is created.  This mirrors the
    behaviour expected by the client which always connects to a clean region.
    """

    for attempt in range(5):
        try:
            shm = shared_memory.SharedMemory(name=name, create=True, size=size)
            logging.info("Created shared memory segment %s (%d bytes)", name, size)
            return shm
        except FileExistsError:  # pragma: no cover - requires prior crash
            logging.warning(
                "Shared memory %s already exists; unlinking and retrying (%d/5)",
                name,
                attempt + 1,
            )
            try:
                existing = shared_memory.SharedMemory(name=name)
                existing.unlink()
                existing.close()
            except FileNotFoundError:
                # Segment vanished between the create attempt and our cleanup.
                pass
            time.sleep(0.1)

    # If creation still fails after retries, fall back to reusing the
    # existing segment so the server can continue operating.
    logging.error(
        "Falling back to existing shared memory segment %s after retries", name
    )
    return shared_memory.SharedMemory(name=name)


def run():
    """Initialize shared memory and launch the NDJSON quote server."""
    logging.basicConfig(level=logging.INFO)
    stock_data_manager = StockDataManager()
    lock = Lock()
    shared_dict = {}

    # Create a shared-memory segment so clients can attach for history reads.
    # The default size (64 MiB) accommodates a reasonably large dataset while
    # still fitting comfortably on modern systems.  If the dataset grows beyond
    # this limit the manager logs an error and skips the write rather than
    # truncating the payload.
    SHM_SIZE = 64 * 1024 * 1024  # 64 MiB
    shm = _ensure_shared_memory("shm0", SHM_SIZE)

    shared_memory_manager = SharedMemoryManager(
        shared_dict,
        lock,
        stock_data_manager,
        shm,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = NDJSONServer(
        shared_memory_manager.quote_cache,
        shared_memory_manager.snapshot_state,
        shm_name=shared_memory_manager.shm_name,
    )
    srv = loop.run_until_complete(server.start("0.0.0.0", 12345))
    try:
        loop.run_forever()
    except KeyboardInterrupt:  # pragma: no cover - graceful shutdown
        pass
    finally:
        srv.close()
        loop.run_until_complete(srv.wait_closed())
        loop.close()
        # Ensure the shared-memory segment is cleaned up when the server
        # shuts down.
        shm.close()
        shm.unlink()


if __name__ == "__main__":
    run()
