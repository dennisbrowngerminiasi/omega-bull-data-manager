import pandas as pd
import yfinance


class StockData:
    def __init__(self, start_date, cur_date, end_date, period, ticker):
        self.start_date = start_date
        self.cur_date = cur_date
        self.end_date = end_date
        self.period = period
        self.ticker = ticker
        self.df = None
        self.download_market_data()

    def download_market_data(self):
        try:
            ticker = yfinance.Ticker(self.ticker)
            self.df = ticker.history(interval=self.period, start=self.start_date, end=self.end_date)
            self.df.columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
            # Check if NA values are in data
            self.df = self.df[self.df['Volume'] != 0]
            self.df.reset_index(inplace=True)
            self.df['Date'] = pd.to_datetime(self.df['Date'])  # Convert 'Date' column to datetime
            self.df.isna().sum()
            print(f"Downloaded data for {self.ticker}")
        except Exception as e:
            print(f"Failed to download data for {self.ticker}: {str(e)}")
            self.df = None
            return {"error": f"Failed to download data for {self.ticker}: {str(e)}"}

    def is_data_empty(self):
        return self.df is None

    def are_all_data_present(self):
        return not self.df.isna().sum().any()

    def to_list(self):
        self.df['Date'] = self.df['Date'].dt.strftime('%Y-%m-%d')  # Convert 'Date' column to string format
        data_list = self.df.to_dict('records')
        for data_dict in data_list:
            data_dict['Ticker'] = self.ticker
        return data_list
