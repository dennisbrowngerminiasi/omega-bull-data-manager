import time
from datetime import datetime
from ib_insync import IB
from stock.stock_data import StockData
from stock.etoro_tickers import EToroTickers

start_date = "2019-10-01"
cur_date = datetime.now()
cur_date_db = cur_date
end_date = cur_date
period = "1d"


class StockDataManager:
    def __init__(self):
        self.scanner_listeners = []
        self.stock_data_list = []
        self.etoro_tickers_list = EToroTickers().list
        self.stop_event = False

        self.ibkr_client = IB()
        self.connect_to_ibkr_tws()

        self.sp500_tickers_list = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "BRK.B", "NVDA", "UNH", "JNJ", "V",
            "XOM", "WMT", "JPM", "META", "PG", "MA", "CVX", "HD", "KO", "PEP",
        ]

    def connect_to_ibkr_tws(self):
        print("Connecting to IBKR TWS")
        self.ibkr_client.connect('127.0.0.1', 7496, clientId=1)
        print("Connected to IBKR TWS: " + str(self.ibkr_client.isConnected()))

    def start_downloader_agent(self):
        print("Start downloader agent")
        self.downloader_agent(60*60)

    def stop_downloader_agent(self):
        print("Stop downloader agent")
        self.stop_event = True

    def downloader_agent(self, periodicity):
        print("Downloader agent started, periodicity: " + str(periodicity) + " seconds")
        time.sleep(1)  # Optional startup delay
        while not self.stop_event:
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
        for listener in self.scanner_listeners:
            listener.on_download_started()

    def notify_listeners_on_download_finished(self):
        print("Notifying listeners on download finished")
        for listener in self.scanner_listeners:
            listener.on_download_finished()

    def register_listener(self, listener):
        print("Registering listener" + str(listener))
        self.scanner_listeners.append(listener)

    def unregister_listener(self, listener):
        print("Unregistering listener" + str(listener))
        self.scanner_listeners.remove(listener)

    def get_all_stock_data(self):
        print("Getting all stock data")
        return self.stock_data_list
