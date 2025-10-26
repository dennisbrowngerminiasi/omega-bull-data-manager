import asyncio
import csv
import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Hardcoded flag that allows developers to skip the expensive download path
# and populate the system with random data instead.  This is useful when
# testing the client integration without waiting for the full stock universe to
# load.
INTEGRATION_TEST_MODE = True

if not INTEGRATION_TEST_MODE:  # pragma: no cover - optional dependency
    from ib_insync import IB
    from stock.stock_data import StockData
    from stock.etoro_tickers import EToroTickers
else:  # Fallback placeholders when running in integration-test mode
    IB = None
    StockData = None
    EToroTickers = None

from utils.paths import CSV_DATA_DIR


logger = logging.getLogger(__name__)

cur_date = datetime.now()
start_date = (cur_date - timedelta(days=365)).strftime("%Y-%m-%d")
cur_date_db = cur_date
end_date = cur_date
period = "1 D"


class StockDataManager:
    def __init__(self):
        self.scanner_listeners = []
        self.stock_data_list = []
        self.stop_event = False
        self.is_downloading = False
        self._offline_data_loaded = False
        self._cached_ranges: Dict[str, Tuple[str, str]] = {}

        self.sp500_tickers_list = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "BRK.B", "NVDA", "UNH", "JNJ", "V",
            "XOM", "WMT", "JPM", "META", "PG", "MA", "CVX", "HD", "KO", "PEP",
        ]

        if INTEGRATION_TEST_MODE:
            # Generate in-memory data for the entire S&P subset without hitting
            # external services.  Previous versions limited this to the first
            # five symbols which caused smoke tests to see only a handful of
            # tickers.  Using the full list keeps the behaviour closer to
            # production while still avoiding network calls.
            self.etoro_tickers_list = self.sp500_tickers_list
            self.ibkr_client = None
        else:  # pragma: no cover - requires external services
            self.etoro_tickers_list = EToroTickers().list
            self.ibkr_client = IB()

        # Always attempt to hydrate from any locally cached CSVs before relying
        # on live market data.  This enables an offline-first startup path and
        # also seeds the manager with the full ticker universe discovered in the
        # cache.
        self.load_local_data()


    def connect_to_ibkr_tws(self):
        print("Connecting to IBKR TWS")

        if INTEGRATION_TEST_MODE:
            if self._offline_data_loaded:
                logger.info(
                    "Offline cache loaded; skipping IBKR connection in integration mode"
                )
            else:
                logger.info(
                    "Integration test mode active; no IBKR client available"
                )
            return False

        # ``ib_insync`` identifies clients by a small integer.  When one is
        # already connected with the same ``clientId`` the TWS instance rejects
        # subsequent connections with error 326.  To cope with lingering
        # sessions, try a handful of different ids before giving up.
        for attempt in range(5):
            client_id = attempt + 1
            try:
                # ``IB.connect`` sets up and stores its own event loop.  The
                # previous implementation used ``asyncio.run`` to call
                # ``connectAsync`` which closed the temporary loop once the call
                # returned, leaving subsequent requests without a running loop
                # and triggering "There is no current event loop" errors.
                # Prefer the synchronous ``connect`` API when available so the
                # loop persists.  Test doubles used in the suite only implement
                # ``connectAsync``, so fall back to manually driving that
                # coroutine in a dedicated loop for compatibility.
                if hasattr(self.ibkr_client, "connect"):
                    self.ibkr_client.connect("127.0.0.1", 7496, clientId=client_id)
                else:  # pragma: no cover - used only by test doubles
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(
                        self.ibkr_client.connectAsync(
                            "127.0.0.1", 7496, clientId=client_id
                        )
                    )
                print(
                    "Connected to IBKR TWS: " + str(self.ibkr_client.isConnected())
                )
                if not self.ibkr_client.isConnected():
                    raise RuntimeError("IBKR connection failed")
                return True
            except Exception as e:  # pragma: no cover - requires real IBKR
                msg = str(e).lower()
                if "client id is already in use" in msg and attempt < 4:
                    print(
                        f"Client ID {client_id} in use, retrying with a different id"
                    )
                    continue
                print(f"Failed to connect to IBKR TWS: {e}")
                break

        self.notify_listeners_on_ibkr_connection_failed()
        return False

    def disconnect_from_ibkr_tws(self):
        """Close the connection to IBKR if one is active.

        IBKR allows only a single client connection.  When an external client
        wishes to take ownership, the server can relinquish its connection via
        this method.  In integration-test mode no real connection exists so the
        method becomes a no-op.
        """
        if INTEGRATION_TEST_MODE:
            self.ibkr_client = None
            return
        if self.ibkr_client is not None and self.ibkr_client.isConnected():
            print("Disconnecting from IBKR TWS")
            self.ibkr_client.disconnect()
            print("Disconnected from IBKR TWS: " + str(self.ibkr_client.isConnected()))

    def start_downloader_agent(self):
        print("Start downloader agent")
        if self._offline_data_loaded:
            try:
                self.reconcile_offline_cache()
            except Exception as reconcile_error:
                logger.error(
                    "Failed to reconcile offline cache before downloader start: %s",
                    reconcile_error,
                )
        if INTEGRATION_TEST_MODE and self._offline_data_loaded:
            logger.info("Offline cache loaded; skipping integration download")
            return
        if INTEGRATION_TEST_MODE:
            self.notify_listeners_on_download_started()
            self.stock_data_list = self._generate_random_data()
            self.notify_listeners_on_download_finished()
        else:
            self.downloader_agent(60*60)

    def stop_downloader_agent(self):
        print("Stop downloader agent")
        self.stop_event = True

    def downloader_agent(self, periodicity):
        print("Downloader agent started, periodicity: " + str(periodicity) + " seconds")
        time.sleep(1)  # Optional startup delay
        while not self.stop_event:
            if not INTEGRATION_TEST_MODE:
                # Ensure we hold a live IBKR connection before attempting the
                # expensive download path.  If the connection is unavailable the
                # manager asks the active client to release it via
                # ``connect_to_ibkr_tws`` and skips this cycle.
                if self.ibkr_client is None or not self.ibkr_client.isConnected():
                    if not self.connect_to_ibkr_tws():
                        print("Skipping download; IBKR not connected")
                        time.sleep(periodicity)
                        continue

            print("Downloading stock data")
            self.notify_listeners_on_download_started()
            self.stock_data_list = StockDataManager.download_stock_data(
                stock_symbols_list=self.etoro_tickers_list,
                ibkr_client=self.ibkr_client
            )
            self.notify_listeners_on_download_finished()
            self.stop_downloader_agent()  # run only once for now

            for _ in range(periodicity):
                time.sleep(1)
                if self.stop_event:
                    break

    @staticmethod
    def download_stock_data(stock_symbols_list, ibkr_client):
        stock_data_list = []

        if ibkr_client is None or not ibkr_client.isConnected():
            raise ValueError("IBKR client not connected")

        for stock_symbol in stock_symbols_list:
            try:
                stock_data = StockData(start_date, cur_date, end_date, period, stock_symbol, ibkr_client)
                if not stock_data.is_data_empty() and stock_data.are_all_data_present():
                    stock_data_list.append(stock_data)
                    stock_data.print_last_candle_open_close_volume()
                    print(f"Downloaded data for {stock_symbol}")
                    print(f"Ticker {stock_symbol} - Last Closing: {stock_data.df['Close'].iloc[-1]}, Last Opening: {stock_data.df['Open'].iloc[-1]}, Last Volume: {stock_data.df['Volume'].iloc[-1]}")
                else:
                    print(f"No valid data for {stock_symbol}")
            except ValueError as e:
                print(f"Failed to download data for {stock_symbol}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred for {stock_symbol}: {e}")

        print("Finished downloading stock data")
        return stock_data_list

    def notify_listeners_on_download_started(self):
        print("Notifying listeners on download started")
        self.is_downloading = True
        for listener in self.scanner_listeners:
            listener.on_download_started()

    def notify_listeners_on_download_finished(self):
        print("Notifying listeners on download finished")
        self.is_downloading = False
        if self.stock_data_list:
            self._offline_data_loaded = True
        for listener in self.scanner_listeners:
            listener.on_download_finished()

    def notify_listeners_on_ibkr_connection_failed(self):
        """Inform listeners that the IBKR connection was lost."""
        for listener in self.scanner_listeners:
            cb = getattr(listener, "on_ibkr_connection_failed", None)
            if cb is not None:
                cb()

    def register_listener(self, listener):
        print("Registering listener" + str(listener))
        self.scanner_listeners.append(listener)

    def unregister_listener(self, listener):
        print("Unregistering listener" + str(listener))
        self.scanner_listeners.remove(listener)

    def get_all_stock_data(self):
        print("Getting all stock data")
        return self.stock_data_list

    # ------------------------------------------------------------------
    # Integration-test helpers
    # ------------------------------------------------------------------
    def _generate_random_data(self):
        """Generate a small set of random stock data without external calls."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        results = []
        for ticker in self.etoro_tickers_list:
            price = round(random.uniform(10, 500), 2)
            volume = random.randint(1_000, 100_000)
            results.append(_RandomStockData(ticker, price, volume, date_str))
        return results

    # ------------------------------------------------------------------
    # Offline cache helpers
    # ------------------------------------------------------------------
    def load_local_data(self):
        """Load cached stock data from CSV files if available."""

        cached_data = []
        try:
            csv_dir = CSV_DATA_DIR
            if not csv_dir.exists():
                return []

            self._cached_ranges.clear()
            for csv_file in sorted(csv_dir.glob("*.csv")):
                ticker = csv_file.stem.upper()
                try:
                    cached_entry = self._load_csv_stock_data(csv_file, ticker)
                    cached_data.append(cached_entry)
                    self._cached_ranges[ticker] = (
                        cached_entry._data["start_date"],
                        cached_entry._data["end_date"],
                    )
                except Exception as csv_error:
                    logger.warning(
                        "Skipping cached data for %s due to error: %s",
                        ticker,
                        csv_error,
                    )

        finally:
            if cached_data:
                cache_tickers = {item.ticker for item in cached_data}
                self.stock_data_list = cached_data
                self._offline_data_loaded = True
                # Ensure the cached tickers are part of the tracked universe so
                # future downloads refresh them as well.
                combined = list({*self.etoro_tickers_list, *cache_tickers})
                combined.sort()
                self.etoro_tickers_list = combined

        return cached_data

    def _load_csv_stock_data(self, csv_path: Path, ticker: str):
        with csv_path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for raw_row in reader:
                if not raw_row:
                    continue
                try:
                    row = {
                        "Date": raw_row["Date"],
                        "Open": float(raw_row["Open"]),
                        "High": float(raw_row["High"]),
                        "Low": float(raw_row["Low"]),
                        "Close": float(raw_row["Close"]),
                        "Volume": int(float(raw_row["Volume"]))
                        if raw_row.get("Volume") not in (None, "")
                        else 0,
                    }
                except (KeyError, ValueError) as err:
                    raise ValueError(
                        f"Malformed row in {csv_path.name}: {raw_row}"
                    ) from err
                rows.append(row)

        if not rows:
            raise ValueError(f"Cached CSV {csv_path.name} contained no data")

        start_date = rows[0]["Date"]
        end_date = rows[-1]["Date"]

        return _CSVStockData(ticker, rows, start_date, end_date)

    # ------------------------------------------------------------------
    # Offline reconciliation helpers
    # ------------------------------------------------------------------
    def reconcile_offline_cache(self) -> None:
        """Download and merge any historical data missing from the cache.

        When the manager is hydrated from CSV files it may lag behind the live
        market data by a few days.  This method determines which tickers require
        updates, fetches only the missing range for each one and persists the
        merged result back to disk so subsequent offline startups remain fast.
        """

        if not self._offline_data_loaded:
            logger.debug("No offline cache loaded; skipping reconciliation")
            return

        missing_ranges = self._determine_missing_ranges()
        if not missing_ranges:
            logger.info("Offline cache already up to date; no reconciliation needed")
            return

        if INTEGRATION_TEST_MODE:
            logger.info(
                "Integration test mode active; skipping provider reconciliation"
            )
            return

        if self.ibkr_client is None or not self.ibkr_client.isConnected():
            if not self.connect_to_ibkr_tws():
                logger.warning(
                    "Unable to reconcile offline cache because IBKR connection is unavailable"
                )
                return

        self.notify_listeners_on_download_started()
        try:
            updates: Dict[str, List[dict]] = {}
            for ticker, (start_date_str, end_date_str) in missing_ranges.items():
                logger.info(
                    "Downloading incremental data for %s from %s to %s",
                    ticker,
                    start_date_str,
                    end_date_str,
                )
                stock_data = self._fetch_incremental_data(
                    ticker, start_date_str, end_date_str
                )
                if stock_data is None:
                    continue
                if getattr(stock_data, "is_data_empty", lambda: False)():
                    continue
                to_dict = stock_data.to_serializable_dict()
                rows = to_dict.get("df") or []
                if not rows:
                    continue
                updates[ticker] = rows

            if updates:
                self._merge_incremental_rows(updates)
        finally:
            self.notify_listeners_on_download_finished()

    def _determine_missing_ranges(self) -> Dict[str, Tuple[str, str]]:
        """Return the date ranges that require refreshing per ticker."""

        if not self.stock_data_list:
            return {}

        today = datetime.utcnow().date()
        if not self._cached_ranges:
            # Build ranges lazily if ``load_local_data`` was bypassed.
            for entry in self.stock_data_list:
                data = getattr(entry, "_data", None)
                if not data:
                    to_dict = getattr(entry, "to_serializable_dict", None)
                    if to_dict is None:
                        continue
                    data = to_dict()
                df_rows = data.get("df") or []
                if not df_rows:
                    continue
                self._cached_ranges[entry.ticker] = (
                    data.get("start_date", df_rows[0]["Date"]),
                    data.get("end_date", df_rows[-1]["Date"]),
                )

        ranges: Dict[str, Tuple[str, str]] = {}
        for ticker, (_, end_date_str) in self._cached_ranges.items():
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(
                    "Cached end date '%s' for %s is invalid; forcing full refresh",
                    end_date_str,
                    ticker,
                )
                ranges[ticker] = (
                    (today - timedelta(days=365)).strftime("%Y-%m-%d"),
                    today.strftime("%Y-%m-%d"),
                )
                continue

            if end_date >= today:
                continue

            missing_start = end_date + timedelta(days=1)
            if missing_start > today:
                continue

            ranges[ticker] = (
                missing_start.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d"),
            )

        return ranges

    def _fetch_incremental_data(
        self, ticker: str, start_date: str, end_date: str
    ):
        """Fetch incremental data for ``ticker`` between the supplied dates."""

        return StockData(
            start_date,
            end_date,
            end_date,
            period,
            ticker,
            self.ibkr_client,
        )

    def _merge_incremental_rows(self, updates: Dict[str, List[dict]]) -> None:
        """Merge provider updates with the cached CSV payloads."""

        current_entries: Dict[str, _CSVStockData] = {
            entry.ticker: entry
            for entry in self.stock_data_list
            if isinstance(entry, _CSVStockData)
        }

        for ticker, rows in updates.items():
            existing = current_entries.get(ticker)
            if existing is None:
                start_date = rows[0]["Date"]
                end_date = rows[-1]["Date"]
                merged_rows = list(rows)
                updated_entry = _CSVStockData(ticker, merged_rows, start_date, end_date)
            else:
                merged_rows = self._merge_rows(existing._data["df"], rows)
                start_date = merged_rows[0]["Date"]
                end_date = merged_rows[-1]["Date"]
                existing._data["df"] = merged_rows
                existing._data["start_date"] = start_date
                existing._data["cur_date"] = end_date
                existing._data["end_date"] = end_date
                updated_entry = existing

            self._persist_csv_rows(ticker, merged_rows)
            self._cached_ranges[ticker] = (start_date, end_date)
            current_entries[ticker] = updated_entry

        merged_list = list(current_entries.values())
        merged_list.sort(key=lambda entry: entry.ticker)
        self.stock_data_list = merged_list

    @staticmethod
    def _merge_rows(existing_rows: Iterable[dict], new_rows: Iterable[dict]) -> List[dict]:
        """Deduplicate and chronologically order cached and provider rows."""

        merged: Dict[str, dict] = {}
        for row in existing_rows:
            merged[row["Date"]] = row
        for row in new_rows:
            merged[row["Date"]] = row

        return [merged[date] for date in sorted(merged.keys())]

    def _persist_csv_rows(self, ticker: str, rows: List[dict]) -> None:
        """Write the merged dataset for ``ticker`` back to the CSV cache."""

        csv_path = CSV_DATA_DIR / f"{ticker}.csv"
        fieldnames = ["Date", "Open", "High", "Low", "Close", "Volume"]
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


class _RandomStockData:
    """Lightweight stock data holder used in integration-test mode."""

    def __init__(self, ticker: str, price: float, volume: int, date: str):
        self.ticker = ticker
        self.df = None
        self._data = {
            "ticker": ticker,
            "start_date": date,
            "cur_date": date,
            "end_date": date,
            "period": "1 D",
            "df": [
                {
                    "Date": date,
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": volume,
                }
            ],
        }

    def to_serializable_dict(self):
        return self._data


class _CSVStockData:
    """Stock data backed by on-disk CSV caches."""

    def __init__(self, ticker: str, rows, start_date: str, end_date: str):
        self.ticker = ticker
        self.df = None
        self._data = {
            "ticker": ticker,
            "start_date": start_date,
            "cur_date": end_date,
            "end_date": end_date,
            "period": "1 D",
            "df": rows,
        }

    def to_serializable_dict(self):
        return self._data
