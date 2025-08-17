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

    # Create a tiny shared-memory segment so clients can attach for history
    # reads.  The SharedMemoryManager only stores data in ``shared_dict`` today,
    # but advertising a real segment prevents clients from failing with
    # ``FileNotFoundError`` when attempting to open the region.
    shm = shared_memory.SharedMemory(name="shm0", create=True, size=1_048_576)

    shared_memory_manager = SharedMemoryManager(
        shared_dict,
        lock,
        stock_data_manager,
        shm_name=shm.name,
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
