import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import utils.client_example as client


def test_main_prints_fundamentals(monkeypatch, capsys):
    monkeypatch.setattr(client, "get_shm_name", lambda: "shm0")
    monkeypatch.setattr(client, "list_tickers", lambda: ["AAPL"])
    monkeypatch.setattr(client, "get_quote", lambda t: {"ticker": t, "price": 1, "volume": 1})
    monkeypatch.setattr(client, "get_history", lambda reader, t: [{"Date": "2024-01-01"}])
    monkeypatch.setattr(client, "read_history_with_epoch", lambda shm, t: [{"Date": "2024-01-01"}])
    monkeypatch.setattr(client, "get_snapshot_epoch", lambda: {"epoch": 1, "last_update_ms": 1})
    monkeypatch.setattr(
        client,
        "get_fundamentals",
        lambda t, fresh=False: {
            "company": {"name": "Apple"},
            "ratios": {"pe_ttm": 30.0},
            "cap_table": {"market_cap": 100.0},
        },
    )

    class DummyReader:
        def __init__(self, host, port, shm_name=None, layout=None):
            pass

    monkeypatch.setattr(client, "StockDataReader", DummyReader)

    logging.basicConfig(level=logging.INFO)
    client.main()
    out = capsys.readouterr().out
    assert "Fundamentals for AAPL" in out
