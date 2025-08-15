from ib_insync import IB, Stock, util
import pandas as pd


class StockData:
    def __init__(self, start_date, cur_date, end_date, period, ticker, ibkr_client):
        self.start_date = start_date
        self.cur_date = cur_date
        self.end_date = end_date
        self.period = period  # e.g., "30 D", "1 Y", etc.
        self.ticker = ticker
        self.ibkr_client = ibkr_client
        self.df = None
        self.ib = IB()
        self.download_market_data()

    def download_market_data(self):
        try:
            contract = Stock(self.ticker.upper(), 'SMART', 'USD')

            # Request all available historical data between the configured start
            # and end dates instead of just a single day. This ensures both the
            # shared memory payload and the persisted CSV contain the full
            # dataset for each ticker.
            start_dt = pd.to_datetime(self.start_date)
            end_dt = pd.to_datetime(self.end_date)
            duration_days = (end_dt - start_dt).days
            duration_str = f"{duration_days} D"
            end_date_str = end_dt.strftime("%Y%m%d %H:%M:%S")

            bars = self.ibkr_client.reqHistoricalData(
                contract,
                endDateTime=end_date_str,
                durationStr=duration_str,
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )

            for bar in bars:
                print(
                    f"{bar.date} | Open: {bar.open} | High: {bar.high} | Low: {bar.low} | Close: {bar.close} | Volume: {bar.volume}")

            self.df = util.df(bars)
            self.df = self.df[['date', 'open', 'high', 'low', 'close', 'volume']]
            self.df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            self.df = self.df[self.df['Volume'] != 0]
            self.df.reset_index(drop=True, inplace=True)
            self.df['Date'] = pd.to_datetime(self.df['Date'])

            print(f"Downloaded data for {self.ticker}")

        except Exception as e:
            print(f"Failed to download data for {self.ticker}: {str(e)}")
            self.df = None

    def is_data_empty(self):
        return self.df is None

    def are_all_data_present(self):
        return not self.df.isna().sum().any()

    def to_list(self):
        self.df['Date'] = self.df['Date'].dt.strftime('%Y-%m-%d')  # Format date as string
        data_list = self.df.to_dict('records')
        for data_dict in data_list:
            data_dict['Ticker'] = self.ticker
        return data_list

    def print_last_candle_open_close_volume(self):
        last_row = self.df.tail(1)
        last_closing = last_row['Close'].item()
        last_opening = last_row['Open'].item()
        last_volume = last_row['Volume'].item()
        print(f"Ticker {self.ticker} - Last Closing: {last_closing}, "
              f"Last Opening: {last_opening}, Last Volume: {last_volume}")

    def to_serializable_dict(self):
        """Prepares the object for writing to shared memory (avoids pickling errors)."""
        if self.df is not None:
            df_serializable = self.df.copy()
            if 'Date' in df_serializable.columns:
                df_serializable['Date'] = df_serializable['Date'].astype(str)  # ✅ Critical Fix
            df_records = df_serializable.to_dict(orient="records")
        else:
            df_records = None

        return {
            "ticker": self.ticker,
            "start_date": self.start_date,
            "cur_date": self.cur_date,
            "end_date": self.end_date,
            "period": self.period,
            "df": df_records
        }
