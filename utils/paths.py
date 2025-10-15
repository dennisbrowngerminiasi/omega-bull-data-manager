"""Common filesystem locations used across the data manager."""

from pathlib import Path


# Directory used to persist historical market data in CSV form.  Both the
# shared-memory manager and the stock data manager rely on the same location so
# that offline startups can hydrate from the cached files before any network
# calls are made.
CSV_DATA_DIR = Path(__file__).resolve().parent.parent / "shared_data_csv"
CSV_DATA_DIR.mkdir(parents=True, exist_ok=True)

