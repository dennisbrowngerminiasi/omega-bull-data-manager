from stock.stock_data import StockData
from stock.stock_data_interface import StockDataInterface


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
            self.lock.acquire()  # Acquire the lock
            for i, stock_data in enumerate(stock_data_list):
                # Convert the StockData object to a dictionary before storing
                stock_data_dict = stock_data.__dict__
                key = f'stock_{i}'
                self.shared_dict[key] = stock_data_dict
                print(f'Key: {key}, Value: {stock_data_dict}')  # Print the key and value
                print(f'Written: Stock data for {stock_data.ticker}')
            self.lock.release()  # Release the lock
        except Exception as e:
            print(f"Error while writing data to shared memory: {e}")
            self.lock.release()  # Release the lock in case of an error
