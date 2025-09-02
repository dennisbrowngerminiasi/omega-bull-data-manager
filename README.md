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

If the data manager cannot connect to Trader Workstation at startup because
another process already holds the lone IBKR session, it logs the failure but
continues running.  The active client can then release the connection via the
`release_ibkr` flow described above.

If the data manager loses its own Trader Workstation connection while a client
holds the reservation, the server sends a `release_ibkr` message with
`{"status":"release_requested"}` to the connected client.  Upon receiving this
request, clients should drop their IBKR session and then send the usual
`release_ibkr` request so the server can reconnect.


### Client integration example

The snippet below shows how a Python client can coordinate access to the single IBKR session:

```python
import asyncio
import json

async def acquire_and_release():
    reader, writer = await asyncio.open_connection("127.0.0.1", 12345)

    # Ask the data manager to relinquish the IBKR connection
    writer.write(b'{"v":1,"id":"acq","type":"acquire_ibkr"}\n')
    await writer.drain()
    resp = json.loads((await reader.readline()).decode())
    if resp["data"]["status"] != "acquired":
        raise RuntimeError(resp["data"].get("reason", "failed"))

    # ... the client connects to IBKR here ...

    # Return control back to the data manager
    writer.write(b'{"v":1,"id":"rel","type":"release_ibkr"}\n')
    await writer.drain()
    print(json.loads((await reader.readline()).decode()))

    writer.close()
    await writer.wait_closed()

asyncio.run(acquire_and_release())
```

Clients should always release the connection when finished so other processes can continue operating.
