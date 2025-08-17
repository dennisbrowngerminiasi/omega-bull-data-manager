# Client Utilities

This directory contains helper code for interacting with the NDJSON quote
server and the shared-memory history.

## `client_example.py`

`client_example.py` is a reference implementation that demonstrates all
supported operations:

1. **`get_shm_name`** – discover the shared-memory segment name used for
   historical data. If the server is not configured with a shared-memory
   region, this request returns an error.
2. **`list_tickers`** – enumerate the tickers backed by shared memory.
3. **`get_quote`** – obtain the most recent price, volume, and metadata for a
   ticker.
4. **`get_snapshot_epoch`** – inspect the global seqlock state to detect when
   data was last written.
5. **`StockDataReader.get_stock`** – read historical bars directly from shared
   memory.

Every request sent to the server must include the fields `v`, `id`, and `type`.
Requests missing any of these fields will be rejected with a `BAD_REQUEST`
error that lists the missing names.

### Running the Example

Ensure the NDJSON quote server is running locally (defaults to `127.0.0.1:12345`)
then execute:

```bash
python utils/client_example.py
```

The script will:

- Log all outbound requests and inbound responses.
- Print the shared-memory segment name.
- Print the available tickers.
- Display the latest quote for the first ticker.
- Show the snapshot epoch metadata.
- Attempt to read history for the first ticker using
  `StockDataReader`. If the shared memory configuration is absent it logs a
  clear error explaining which values are required.

### Shared Memory Configuration

Reading history requires the name of the shared-memory segment obtained from
the data manager. Servers running without a shared-memory region will return a
`NOT_FOUND` error to `get_shm_name` and history reads should be skipped.

Pass the advertised segment name to `StockDataReader`:

```python
from shared_memory.shared_memory_reader import StockDataReader

reader = StockDataReader(host, port, shm_name="stocks")
rows = reader.get_stock("AAPL")
print("first close", rows["df"][0]["Close"])
```

The example reader in this repository opens the shared-memory segment directly
and retries if it encounters an inconsistent seqlock epoch, logging detailed
information about each attempt.
