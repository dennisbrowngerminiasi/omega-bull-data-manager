# IBKR Connection Coordination API Task

## Objective
Implement client-side support for the Omega Bull Data Manager's IBKR connection coordination API. Clients must synchronize usage of the single Trader Workstation (TWS) session by explicitly acquiring and releasing the connection before interacting with IBKR.

The server will automatically retry its own IBKR connection with up to five
different `clientId` values if the initially chosen identifier is already in
use, but clients still need to coordinate using the API below to avoid
conflicts.

## Endpoints
The NDJSON server exposes two new request types over the existing TCP interface:

1. **acquire_ibkr**  
   Ask the data manager to relinquish its IBKR connection.
   - **Request**: `{"v":1, "id":"<unique>", "type":"acquire_ibkr"}`
   - **Success Response**: `{"v":1, "id":"<unique>", "type":"response", "op":"acquire_ibkr", "data":{"status":"acquired"}}`
   - **Conflict**: Returned when another client holds the reservation. Error response code: `CONFLICT`.
   - **Download In Progress**: Returned when stock data is currently downloading. Error response code: `DENIED` with reason `wait until stock download is finished`.

2. **release_ibkr**  
   Return control of the IBKR connection to the data manager once finished.
   - **Request**: `{"v":1, "id":"<unique>", "type":"release_ibkr"}`
   - **Success Response**: `{"v":1, "id":"<unique>", "type":"response", "op":"release_ibkr", "data":{"status":"released"}}`
   - **Without Reservation**: If no client holds the reservation, the server replies with error code `BAD_REQUEST`.

## Workflow
1. Connect to the NDJSON server (default `127.0.0.1:12345`).
2. Send an `acquire_ibkr` request and wait for a response.
3. If `status` is `acquired`, safely establish the client's IBKR TWS connection.
4. Perform required IBKR operations.
5. Send a `release_ibkr` request to let the server reconnect to IBKR.
6. Close the TCP connection.

## Example (Python)
```python
import asyncio, json

async def acquire_and_release():
    reader, writer = await asyncio.open_connection("127.0.0.1", 12345)

    writer.write(b'{"v":1,"id":"acq","type":"acquire_ibkr"}\n')
    await writer.drain()
    resp = json.loads((await reader.readline()).decode())
    if resp["data"]["status"] != "acquired":
        raise RuntimeError(resp["data"].get("reason", "failed"))

    # ... establish IBKR connection ...

    writer.write(b'{"v":1,"id":"rel","type":"release_ibkr"}\n')
    await writer.drain()
    await reader.readline()

    writer.close()
    await writer.wait_closed()

asyncio.run(acquire_and_release())
```

## Acceptance Criteria
- The client must always request `acquire_ibkr` before connecting to IBKR.
- The client must handle denial responses gracefully and retry after downloads finish.
- The client must call `release_ibkr` when finished to allow other processes to use IBKR.

