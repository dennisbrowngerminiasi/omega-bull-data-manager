import asyncio
import json
from multiprocessing import Manager, Lock
from pathlib import Path
import sys

import pytest

# Ensure repository root on path for module imports
sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared_memory.shared_memory_manager import SharedMemoryManager
from quote_server import NDJSONServer


class FakeStockData:
    def __init__(self, ticker: str, price: float, volume: int, date: str = "2024-01-01"):
        self.ticker = ticker
        self.df = None  # avoiding pandas dependency
        self._data = {
            "ticker": ticker,
            "start_date": date,
            "cur_date": date,
            "end_date": date,
            "period": "1 D",
            "df": [
                {
                    "Date": date,
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": volume,
                }
            ],
        }

    def to_serializable_dict(self):
        return self._data


class FakeDataManager:
    def __init__(self, stock_data_list):
        self.stock_data_list = stock_data_list
        self.scanner_listeners = []

    def register_listener(self, listener):
        self.scanner_listeners.append(listener)

    def start_downloader_agent(self):
        for l in self.scanner_listeners:
            l.on_download_started()
        for l in self.scanner_listeners:
            l.on_download_finished()

    def get_all_stock_data(self):
        return self.stock_data_list


async def send_request(port, obj):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(json.dumps(obj).encode() + b"\n")
    await writer.drain()
    resp_line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(resp_line.decode())


def test_server_endpoints():
    async def run_test():
        mgr = Manager()
        shared_dict = mgr.dict()
        lock = Lock()

        fake_data = [
            FakeStockData("AAPL", 100.0, 10),
            FakeStockData("MSFT", 200.0, 20),
        ]
        fdm = FakeDataManager(fake_data)
        smm = SharedMemoryManager(shared_dict, lock, fdm)

        server = NDJSONServer(smm.quote_cache, smm.snapshot_state)
        srv = await server.start("127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]

        # list_tickers
        resp = await send_request(port, {"v": 1, "id": "1", "type": "list_tickers"})
        assert set(resp["data"]) == {"AAPL", "MSFT"}

        # get_quote success
        resp = await send_request(port, {"v": 1, "id": "2", "type": "get_quote", "ticker": "AAPL"})
        assert resp["data"]["price"] == 100.0
        assert resp["data"]["ticker"] == "AAPL"

        # get_quote not found
        resp = await send_request(port, {"v": 1, "id": "3", "type": "get_quote", "ticker": "GOOG"})
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "NOT_FOUND"

        # malformed JSON
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"not json\n")
        await writer.drain()
        resp_line = await reader.readline()
        writer.close()
        await writer.wait_closed()
        resp = json.loads(resp_line.decode())
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "BAD_REQUEST"

        # oversize line
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"{" + b"a" * 70000 + b"}\n")
        await writer.drain()
        resp_line = await reader.readline()
        writer.close()
        await writer.wait_closed()
        resp = json.loads(resp_line.decode())
        assert resp["type"] == "error"
        assert resp["error"]["code"] == "BAD_REQUEST"

        srv.close()
        await srv.wait_closed()
        mgr.shutdown()

    asyncio.run(run_test())
