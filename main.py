from multiprocessing import Lock, Manager
from shared_memory.shared_memory_manager import SharedMemoryManager
from server.server import Server
from stock.stock_data_manager import StockDataManager
from shared_memory.shared_dict_manager import SharedDictManager, get_shared_dict

if __name__ == "__main__":
    stock_data_manager = StockDataManager()
    lock = Lock()  # Create a Lock object
    manager = Manager()  # Create a Manager object
    shared_dict = manager.dict()  # Create a shared dictionary
    shared_memory_manager = SharedMemoryManager(shared_dict, lock, stock_data_manager)  # Pass the shared_dict, Lock object, and stock_data_manager

    SharedDictManager.register('get_shared_dict', callable=lambda: get_shared_dict(shared_dict))
    shared_dict_manager = SharedDictManager(address=('', 50000), authkey=b'abc')
    server = shared_dict_manager.get_server()
    server.serve_forever()