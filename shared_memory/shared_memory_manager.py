from pathlib import Path
import os
import time
from typing import Optional
from stock.stock_data_interface import StockDataInterface


CSV_DATA_DIR = Path(__file__).resolve().parent.parent / "shared_data_csv"
CSV_DATA_DIR.mkdir(parents=True, exist_ok=True)


class SharedMemoryManager(StockDataInterface):

    def __init__(self, shared_dict, lock, stock_data_manager, shm_name: Optional[str] = None):
        self.shared_dict = shared_dict
        self.lock = lock
        self.stock_data_manager = stock_data_manager
        self.stock_data_manager.register_listener(self)

        # Optional name of a real shared-memory segment backing historical data.
        # In environments that don't expose such a segment (e.g. tests or the
        # lightweight integration mode), ``shm_name`` may be ``None`` and the
        # NDJSON server will report that shared memory is unavailable.
        self.shm_name = shm_name

        # In-memory cache for the most recent quote of each ticker. The server
        # reads from this structure to serve `get_quote` requests in O(1)
        # without touching the historical data stored in the shared dictionary.
        self.quote_cache = {}

        # Global snapshot state used by the server to report the last update
        # epoch and timestamp. The epoch follows a seqlock style scheme where
        # odd numbers indicate that a write is in progress.
        self.snapshot_state = {"epoch": 0, "last_update_ms": 0}

        self.writer_pid = os.getpid()

        self.stock_data_manager.start_downloader_agent()

    def on_download_started(self):
        pass

    def on_download_finished(self):
        all_stock_data = self.stock_data_manager.get_all_stock_data()
        self.write_data(all_stock_data)

    def write_data(self, stock_data_list):
        print("Writing data to shared memory----------------------------------------------@@@@@@@")
        try:
            with self.lock:
                # Increment the global snapshot epoch to an odd number to signal
                # that an update is in progress. Readers of the shared memory can
                # detect this and retry until the epoch becomes even again.
                self.snapshot_state["epoch"] += 1

                # Use the actual ticker symbol as the key in shared memory so clients
                # can access stock data by the expected ticker name instead of a
                # generated index like "stock_0".  This ensures the shared memory
                # keys accurately reflect the underlying data and matches the
                # expectations of consumers of this module.
                for stock_data in stock_data_list:
                    key = stock_data.ticker

                    # Retrieve existing entry or create a new one with a seqlock
                    # style header.  The header fields allow readers to determine
                    # whether they have observed a consistent snapshot.
                    entry = self.shared_dict.get(
                        key,
                        {
                            "header": {
                                "version": 1,
                                "epoch": 0,
                                "last_update_ms": 0,
                                "writer_pid": self.writer_pid,
                            },
                            "data": None,
                        },
                    )

                    # Mark the entry as being written by incrementing the epoch to
                    # an odd number before publishing any changes.
                    entry["header"]["epoch"] += 1
                    self.shared_dict[key] = entry

                    data_dict = stock_data.to_serializable_dict()

                    now_ms = int(time.time() * 1000)
                    entry["data"] = data_dict
                    entry["header"]["last_update_ms"] = now_ms
                    entry["header"]["epoch"] += 1
                    self.shared_dict[key] = entry

                    # Update in-memory quote cache for fast `get_quote` lookups.
                    try:
                        if data_dict.get("df"):
                            last = data_dict["df"][-1]
                            ts_ms = int(
                                time.mktime(time.strptime(last["Date"], "%Y-%m-%d"))
                                * 1000
                            )
                            self.quote_cache[key] = {
                                "price": last.get("Close"),
                                "volume": last.get("Volume"),
                                "currency": "USD",
                                "ts_epoch_ms": ts_ms,
                                "source": "shared_memory_manager",
                            }
                    except Exception as cache_error:
                        print(f"Error updating quote cache for {key}: {cache_error}")

                    try:
                        if stock_data.df is not None:
                            csv_path = CSV_DATA_DIR / f"{stock_data.ticker}.csv"
                            stock_data.df.to_csv(csv_path, index=False)
                    except Exception as csv_error:
                        print(f"Error while saving CSV for {stock_data.ticker}: {csv_error}")

                # Finalize global snapshot epoch to an even value and record the
                # last update timestamp.
                self.snapshot_state["last_update_ms"] = int(time.time() * 1000)
                self.snapshot_state["epoch"] += 1
        except Exception as e:
            print(f"Error while writing data to shared memory: {e}")
            raise
        print("finished writing data to shared memory")

