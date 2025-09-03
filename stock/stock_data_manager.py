import asyncio
import time
import random
from datetime import datetime, timedelta

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


    def connect_to_ibkr_tws(self):
        print("Connecting to IBKR TWS")

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
