import pandas as pd

DEBUG_MODE_ON = False


class EToroTickers:
    def __init__(self):
        self.list = []
        self.initialize()

    def initialize(self):
        data = pd.read_csv("tickers_files/etoro_tickers.csv")
        self.list = data.Ticker
        if DEBUG_MODE_ON:
            self.list = self.list.tail(10)
