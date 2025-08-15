import time
from datetime import datetime, timezone
from types import SimpleNamespace
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.server import app
from api.deps import PriceCache


class DummyStock:
    def __init__(self, symbol: str, price: float):
        now = datetime.now(timezone.utc)
        self.ticker = symbol
        self.df = pd.DataFrame([{"Date": now, "Close": price}])


def create_client():
    mgr = SimpleNamespace(stock_data_list=[
        DummyStock("AAPL", 100.0),
        DummyStock("MSFT", 200.0),
    ])
    app.state.cache = PriceCache(mgr)
    app.state.start_time = time.time()
    app.state.uptime = lambda: 0
    return TestClient(app)


@pytest.fixture
def client():
    return create_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_price(client):
    resp = client.get("/v1/price", params={"symbol": "AAPL"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["price"] == 100.0


def test_batch(client):
    resp = client.post("/v1/prices", json={"symbols": ["AAPL", "MSFT", "BAD"]})
    assert resp.status_code == 200
    res = {r["symbol"]: r for r in resp.json()["results"]}
    assert res["AAPL"]["status"] == "ok"
    assert res["MSFT"]["status"] == "ok"
    assert res["BAD"]["status"] == "error"
    assert res["BAD"]["error_code"] == "SYMBOL_NOT_FOUND"


def test_auth(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "t")
    client = create_client()
    r = client.get("/v1/price", params={"symbol": "AAPL"})
    assert r.status_code == 401
    r2 = client.get(
        "/v1/price",
        params={"symbol": "AAPL"},
        headers={"Authorization": "Bearer t"},
    )
    assert r2.status_code == 200
    monkeypatch.delenv("AUTH_TOKEN")
