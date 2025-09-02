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


class DummyDataManager:
    def __init__(self):
        self.disconnect_called = False
        self.connect_called = False
        self.is_downloading = False
        self.listeners = []

    def register_listener(self, listener):
        self.listeners.append(listener)

    def start_downloader_agent(self):
        pass

    def disconnect_from_ibkr_tws(self):
        self.disconnect_called = True

    def connect_to_ibkr_tws(self):
        self.connect_called = True

    def get_all_stock_data(self):
        return []


async def send(port, payload):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(json.dumps(payload).encode() + b"\n")
    await writer.drain()
    resp = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(resp.decode())


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

        # acquire connection
        resp = await send(port, {"v": 1, "id": "a1", "type": "acquire_ibkr"})
        assert resp["data"]["status"] == "acquired"
        assert dm.disconnect_called is True

        # second acquisition should conflict
        resp = await send(port, {"v": 1, "id": "a2", "type": "acquire_ibkr"})
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "CONFLICT"

        # release connection
        resp = await send(port, {"v": 1, "id": "r1", "type": "release_ibkr"})
        assert resp["data"]["status"] == "released"
        assert dm.connect_called is True

        # releasing again should error
        resp = await send(port, {"v": 1, "id": "r2", "type": "release_ibkr"})
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "BAD_REQUEST"

        # acquisition denied during download
        dm.is_downloading = True
        resp = await send(port, {"v": 1, "id": "a3", "type": "acquire_ibkr"})
        assert resp["data"]["status"] == "denied"
        assert resp["data"]["reason"] == "wait until stock download is finished"
        dm.is_downloading = False

        srv.close()
        await srv.wait_closed()
        shm.close()
        shm.unlink()

    asyncio.run(run_test())
