import asyncio
import json
from threading import Lock
from pathlib import Path
import sys
from multiprocessing import shared_memory

# Ensure repo root on path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from quote_server import NDJSONServer
from shared_memory.shared_memory_manager import SharedMemoryManager
from utils import client_example as client


class DummyDataManager:
    def __init__(self):
        self.disconnect_called = False
        self.connect_called = False
        self.is_downloading = False
        self.listeners = []

    def register_listener(self, listener):
        self.listeners.append(listener)

    def notify_ibkr_connection_failed(self):
        for l in self.listeners:
            cb = getattr(l, "on_ibkr_connection_failed", None)
            if cb:
                cb()

    def start_downloader_agent(self):
        pass

    def disconnect_from_ibkr_tws(self):
        self.disconnect_called = True

    def connect_to_ibkr_tws(self):
        self.connect_called = True

    def get_all_stock_data(self):
        return []


def test_ibkr_acquire_release_flow():
    async def run_test():
        shared_dict = {}
        lock = Lock()
        dm = DummyDataManager()
        shm = shared_memory.SharedMemory(create=True, size=16)
        smm = SharedMemoryManager(shared_dict, lock, dm, shm)

        server = NDJSONServer(
            smm.quote_cache,
            smm.snapshot_state,
            smm.shm_name,
            stock_data_manager=dm,
        )
        srv = await server.start("127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]

        client.HOST = "127.0.0.1"
        client.PORT = port

        # acquire connection
        resp = await asyncio.to_thread(client.acquire_ibkr)
        assert resp["status"] == "acquired"
        assert dm.disconnect_called is True

        # second acquisition should conflict
        resp = await asyncio.to_thread(client._send, {"v": 1, "id": "a2", "type": "acquire_ibkr"})
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "CONFLICT"

        # release connection
        resp = await asyncio.to_thread(client.release_ibkr)
        assert resp["status"] == "released"
        assert dm.connect_called is True

        # releasing again should error
        resp = await asyncio.to_thread(client._send, {"v": 1, "id": "r2", "type": "release_ibkr"})
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "BAD_REQUEST"

        # acquisition denied during download
        dm.is_downloading = True
        resp = await asyncio.to_thread(client.acquire_ibkr)
        assert resp["status"] == "denied"
        assert resp["reason"] == "wait until stock download is finished"
        dm.is_downloading = False

        srv.close()
        await srv.wait_closed()
        shm.close()
        shm.unlink()

    asyncio.run(run_test())


def test_server_requests_release_on_failure():
    async def run_test():
        shared_dict = {}
        lock = Lock()
        dm = DummyDataManager()
        shm = shared_memory.SharedMemory(create=True, size=16)
        smm = SharedMemoryManager(shared_dict, lock, dm, shm)

        server = NDJSONServer(
            smm.quote_cache,
            smm.snapshot_state,
            smm.shm_name,
            stock_data_manager=dm,
        )
        srv = await server.start("127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]

        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        writer.write(b'{"v":1,"id":"acq","type":"acquire_ibkr"}\n')
        await writer.drain()
        resp = json.loads((await reader.readline()).decode())
        assert resp["data"]["status"] == "acquired"

        await asyncio.get_running_loop().run_in_executor(None, dm.notify_ibkr_connection_failed)
        msg = json.loads((await reader.readline()).decode())
        assert msg["op"] == "release_ibkr"
        assert msg["data"]["status"] == "release_requested"

        writer.write(b'{"v":1,"id":"rel","type":"release_ibkr"}\n')
        await writer.drain()
        resp = json.loads((await reader.readline()).decode())
        assert resp["data"]["status"] == "released"

        writer.close()
        await writer.wait_closed()

        srv.close()
        await srv.wait_closed()
        shm.close()
        shm.unlink()

    asyncio.run(run_test())
