import asyncio
import logging
from threading import Lock
from multiprocessing import shared_memory

from shared_memory.shared_memory_manager import SharedMemoryManager
from stock.stock_data_manager import StockDataManager
from quote_server import NDJSONServer


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
    shm = shared_memory.SharedMemory(name="shm0", create=True, size=SHM_SIZE)
    logging.info("Created shared memory segment %s (%d bytes)", shm.name, shm.size)

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
