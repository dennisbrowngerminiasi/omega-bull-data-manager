# IBKR Release Request Handling Task

## Objective
Ensure the client responds when the data manager asks it to relinquish the lone Interactive Brokers connection.

## Background
If the server loses its own connection to Trader Workstation while a client holds the reservation, it will send a message requesting the client to release IBKR:

```json
{"v":1, "type":"response", "op":"release_ibkr", "data":{"status":"release_requested"}}
```

## Tasks
- Detect inbound `release_ibkr` messages where `data.status` is `release_requested`.
- Gracefully disconnect from IBKR and clean up any in‑flight work.
- Send the usual `release_ibkr` request back to the data manager to confirm the release.

## Acceptance Criteria
- The client drops its IBKR connection promptly after receiving the request.
- The server acknowledges with `{..."op":"release_ibkr","data":{"status":"released"}}`.
