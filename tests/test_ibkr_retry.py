import asyncio
import types

from stock import stock_data_manager as sdm


class DummyIB:
    def __init__(self):
        self.calls = []
        self.connected = False

    async def connectAsync(self, host, port, clientId):
        self.calls.append(clientId)
        # Fail for first four attempts to simulate client id conflicts
        if len(self.calls) < 5:
            raise Exception("client id is already in use")
        self.connected = True

    def isConnected(self):
        return self.connected


class DummyTickers:
    def __init__(self):
        self.list = []


def test_retry_different_client_ids(monkeypatch):
    # Enable non integration mode with dummy dependencies
    monkeypatch.setattr(sdm, "INTEGRATION_TEST_MODE", False)
    monkeypatch.setattr(sdm, "IB", DummyIB)
    monkeypatch.setattr(sdm, "EToroTickers", DummyTickers)

    mgr = sdm.StockDataManager()
    assert mgr.connect_to_ibkr_tws() is True
    assert mgr.ibkr_client.calls == [1, 2, 3, 4, 5]
