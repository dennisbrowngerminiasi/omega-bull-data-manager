import threading
import time
from datetime import datetime
from tqdm import tqdm

from stock.stock_data import StockData
from stock.etoro_tickers import EToroTickers
from ib_insync import *

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
        self.stop_event = threading.Event()

        self.ibkr_client = IB()
        self.connect_to_ibkr_tws()
        self.downloader_thread = threading.Thread(target=self.downloader_agent, args=(60 * 60 * 60,))
        self.sp500_tickers_list = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "BRK.B", "NVDA", "UNH", "JNJ", "V",
            "XOM", "WMT", "JPM", "META", "PG", "MA", "CVX", "HD", "KO", "PEP",
            # Add the remaining S&P 500 tickers here
        ]
       # self.download_stock_data(self.etoro_tickers_list)


    # TODO: share the data via http passing a json file??

    def register_listener(self, listener):
        print("Registering listener" + str(listener))
        self.scanner_listeners.append(listener)


    def unregister_listener(self, listener):
        print("Unregistering listener" + str(listener))
        self.scanner_listeners.remove(listener)


    def download_stock_data(self, stock_symbols_list):
        self.stock_data_list = []

        if not self.ibkr_client.isConnected():
            self.connect_to_ibkr_tws()

        for stock_symbol in tqdm(stock_symbols_list, desc="Downloading stock data"):
            try:
                stock_data = StockData(start_date, cur_date, end_date, period, stock_symbol, self.ibkr_client)
                if not stock_data.is_data_empty() and stock_data.are_all_data_present():
                    self.stock_data_list.append(stock_data)
                    stock_data.print_last_candle_open_close_volume()
                    tqdm.write(f"Downloaded data for {stock_symbol}")
                    tqdm.write(
                        f"Ticker {stock_symbol} - Last Closing: {stock_data.df['Close'].iloc[-1]}, Last Opening: {stock_data.df['Open'].iloc[-1]}, Last Volume: {stock_data.df['Volume'].iloc[-1]}")
                else:
                    tqdm.write(f"No valid data for {stock_symbol}")
            except ValueError as e:
                tqdm.write(f"Failed to download data for {stock_symbol}: {e}")
            except Exception as e:
                tqdm.write(f"An unexpected error occurred for {stock_symbol}: {e}")

        self.ibkr_client.disconnect()
        print("Finished downloading stock data")
        print("Disconnecting from IBKR TWS")


    def notify_listeners_on_download_finished(self):
        print("Notifying listeners on download finished")
        if self.scanner_listeners is not None:
            for listener in self.scanner_listeners:
                listener.on_download_finished()


    def notify_listeners_on_download_started(self):
        print("Notifying listeners on download started")
        if self.scanner_listeners is not None:
            for listener in self.scanner_listeners:
                listener.on_download_started()


    def stop_downloader_agent(self):
        print("Stop downloader agent")
        self.stop_event.set()


    def start_downloader_agent(self):
        print("Start downloader agent")
        self.downloader_thread.start()


    def downloader_agent(self, periodicity):
        print("Downloader agent started, periodicity: " + str(periodicity) + " seconds")
        time.sleep(10)  # Allow some time for the thread to start properly
        while not self.stop_event.is_set():
            print("Downloading stock data")
            self.notify_listeners_on_download_started()
            self.download_stock_data(self.etoro_tickers_list)
            self.notify_listeners_on_download_finished()
            #let's finish it for now !!!!!!!!!!!!!!!!!!!
            self.stop_downloader_agent()

            for _ in range(periodicity):
                time.sleep(1)
                if self.stop_event.is_set():
                    break


    def get_all_stock_data(self):
        print("Getting all stock data")
        return self.stock_data_list


    def connect_to_ibkr_tws(self):
        print("Connecting to IBKR TWS")
        self.ibkr_client.connect('127.0.0.1', 7496, clientId=1)
        print("Connected to IBKR TWS: " + str(self.ibkr_client.isConnected()))


