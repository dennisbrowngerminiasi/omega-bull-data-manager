import csv
import os
from datetime import datetime, timezone
from threading import RLock
from typing import Optional


class PriceCache:
    def __init__(self, stock_data_manager):
        self.mgr = stock_data_manager
        self.lock = RLock()

    def _to_iso(self, value) -> str:
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = value.to_pydatetime()  # pandas Timestamp
            except AttributeError:
                dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()

    def get_latest(self, symbol: str) -> Optional[dict]:
        sym = symbol.upper()
        with self.lock:
            for sd in getattr(self.mgr, "stock_data_list", []):
                if getattr(sd, "ticker", "").upper() == sym:
                    df = getattr(sd, "df", None)
                    if df is not None and not df.empty:
                        price = float(df["Close"].iloc[-1])
                        as_of_val = df["Date"].iloc[-1]
                        as_of = self._to_iso(as_of_val)
                        return {
                            "price": price,
                            "as_of": as_of,
                            "currency": "USD",
                            "source": "memory",
                        }
            path = os.path.join("shared_data_csv", f"{sym}.csv")
            if os.path.exists(path):
                try:
                    with open(path, newline="") as fh:
                        reader = csv.DictReader(fh)
                        last_row = None
                        for last_row in reader:
                            pass
                    if last_row and "Close" in last_row and "Date" in last_row:
                        price = float(last_row["Close"])
                        as_of = self._to_iso(last_row["Date"])
                        return {
                            "price": price,
                            "as_of": as_of,
                            "currency": "USD",
                            "source": "csv",
                        }
                except Exception:
                    pass
        return None
