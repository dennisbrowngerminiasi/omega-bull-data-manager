from pathlib import Path
from stock.stock_data import StockData
from stock.stock_data_interface import StockDataInterface


CSV_DATA_DIR = Path(__file__).resolve().parent.parent / "shared_data_csv"
CSV_DATA_DIR.mkdir(parents=True, exist_ok=True)


class SharedMemoryManager(StockDataInterface):

    def __init__(self, shared_dict, lock, stock_data_manager):
        self.shared_dict = shared_dict
        self.lock = lock
        self.stock_data_manager = stock_data_manager
        self.stock_data_manager.register_listener(self)
        self.stock_data_manager.start_downloader_agent()

    def on_download_started(self):
        pass

    def on_download_finished(self):
        all_stock_data = self.stock_data_manager.get_all_stock_data()
        self.write_data(all_stock_data)

    def write_data(self, stock_data_list):
        try:
            print("Writing data to shared memory----------------------------------------------@@@@@@@")
            self.lock.acquire()

            # Use the actual ticker symbol as the key in shared memory so clients
            # can access stock data by the expected ticker name instead of a
            # generated index like "stock_0".  This ensures the shared memory
            # keys accurately reflect the underlying data and matches the
            # expectations of consumers of this module.
            for stock_data in stock_data_list:
                key = stock_data.ticker
                self.shared_dict[key] = stock_data.to_serializable_dict()

                try:
                    if stock_data.df is not None:
                        csv_path = CSV_DATA_DIR / f"{stock_data.ticker}.csv"
                        stock_data.df.to_csv(csv_path, index=False)
                except Exception as csv_error:
                    print(f"Error while saving CSV for {stock_data.ticker}: {csv_error}")

            self.lock.release()
            print("finished writing data to shared memory")
        except Exception as e:
            print(f"Error while writing data to shared memory: {e}")
            self.lock.release()

