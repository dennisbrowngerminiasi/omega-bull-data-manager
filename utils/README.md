# Client Utilities

This directory contains helper code for interacting with the NDJSON quote
server and the shared-memory history.

## `client_example.py`

`client_example.py` is a reference implementation that demonstrates all
supported operations:

1. **`list_tickers`** – enumerate the tickers backed by shared memory.
2. **`get_quote`** – obtain the most recent price, volume, and metadata for a
ticker.
3. **`get_snapshot_epoch`** – inspect the global seqlock state to detect when
   data was last written.
4. **`StockDataReader.get_stock`** – read historical bars directly from shared
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
- Print the available tickers.
- Display the latest quote for the first ticker.
- Show the snapshot epoch metadata.
- Attempt to read history for the first ticker using
  `StockDataReader`. If the shared memory configuration is absent it logs a
  clear error explaining which values are required.

### Shared Memory Configuration

Reading history requires two pieces of information obtained from the data
manager:

- **`shm_name`** – name of the shared-memory segment containing historical
  data.
- **`layout`** – mapping of ticker symbols to their offset/size information
  inside the segment.

Pass these values to `StockDataReader`:

```python
from shared_memory.shared_memory_reader import StockDataReader

reader = StockDataReader(host, port, shm_name="stocks", layout=ticker_layout)
rows = reader.get_stock("AAPL")
print("first close", rows[0]["Close"])
```

The example ships with a minimal reader that mirrors the error a client would
receive if the shared-memory configuration is not supplied. Replace it with a
real implementation when integrating with the production data manager.
