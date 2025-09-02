# Omega Bull Data Manager

This service exposes an NDJSON TCP API that allows clients to discover
available tickers, fetch quotes and interact with the shared-memory snapshot
produced by the downloader agent.

## IBKR connection coordination

Both the data manager and external clients may need to access an Interactive
Brokers (IBKR) Trader Workstation.  IBKR only permits a single active
connection, so the server now exposes a simple request/response mechanism to
coordinate access.

### Acquire the IBKR connection

When a client wishes to connect to IBKR it should first ask the data manager to
relinquish its connection:

```json
{"v":1, "id":"acq", "type":"acquire_ibkr"}
```

If available the server responds:

```json
{"v":1, "id":"acq", "type":"response", "op":"acquire_ibkr", "data":{"status":"acquired"}}
```

The client can now safely establish its own IBKR connection.  While reserved,
additional `acquire_ibkr` requests return an error with code `CONFLICT`.

If a stock download is in progress the request is denied:

```json
{"v":1, "id":"acq", "type":"response", "op":"acquire_ibkr", "data":{"status":"denied","reason":"wait until stock download is finished"}}
```

### Release the IBKR connection

After the client is done it should release the reservation so the data manager
can reconnect:

```json
{"v":1, "id":"rel", "type":"release_ibkr"}
```

The server acknowledges the release:

```json
{"v":1, "id":"rel", "type":"response", "op":"release_ibkr", "data":{"status":"released"}}
```

Issuing `release_ibkr` without a prior reservation results in an error with
code `BAD_REQUEST`.

These endpoints allow multiple clients and the data manager to cooperate and
avoid simultaneous IBKR connections.

