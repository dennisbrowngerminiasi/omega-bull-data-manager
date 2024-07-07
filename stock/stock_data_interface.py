from abc import ABC, abstractmethod


class StockDataInterface(ABC):

    @abstractmethod
    def on_download_started(self):
        pass

    @abstractmethod
    def on_download_finished(self):
        pass
