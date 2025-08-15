import asyncio
import logging
from threading import Lock

from shared_memory.shared_memory_manager import SharedMemoryManager
from stock.stock_data_manager import StockDataManager
from quote_server import NDJSONServer


def run():
    """Initialize shared memory and launch the NDJSON quote server."""
    logging.basicConfig(level=logging.INFO)
    stock_data_manager = StockDataManager()
    lock = Lock()
    shared_dict = {}
    shared_memory_manager = SharedMemoryManager(shared_dict, lock, stock_data_manager)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = NDJSONServer(
        shared_memory_manager.quote_cache, shared_memory_manager.snapshot_state
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


if __name__ == "__main__":
    run()
