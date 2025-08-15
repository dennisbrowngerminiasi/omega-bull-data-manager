from multiprocessing import Lock, Manager
from threading import Thread
import asyncio

from shared_memory.shared_memory_manager import SharedMemoryManager
from stock.stock_data_manager import StockDataManager
from shared_memory.shared_dict_manager import SharedDictManager, get_shared_dict
from quote_server import NDJSONServer


def _start_quote_server(quote_cache, snapshot_state, host="0.0.0.0", port=12345):
    """Start the NDJSON quote server in a dedicated event-loop thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = NDJSONServer(quote_cache, snapshot_state)
    srv = loop.run_until_complete(server.start(host, port))
    try:
        loop.run_forever()
    finally:
        srv.close()
        loop.run_until_complete(srv.wait_closed())
        loop.close()


def run():
    """Initialize shared memory and launch both shared dict and quote servers."""
    stock_data_manager = StockDataManager()
    lock = Lock()
    manager = Manager()
    shared_dict = manager.dict()
    shared_memory_manager = SharedMemoryManager(shared_dict, lock, stock_data_manager)

    # Launch the quote server in the background so it runs alongside the
    # shared dictionary server.
    quote_thread = Thread(
        target=_start_quote_server,
        args=(shared_memory_manager.quote_cache, shared_memory_manager.snapshot_state),
        daemon=True,
    )
    quote_thread.start()

    SharedDictManager.register("get_shared_dict", callable=lambda: get_shared_dict(shared_dict))
    shared_dict_manager = SharedDictManager(address=("", 50000), authkey=b"abc")
    server = shared_dict_manager.get_server()

    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - graceful shutdown
        pass


if __name__ == "__main__":
    run()
