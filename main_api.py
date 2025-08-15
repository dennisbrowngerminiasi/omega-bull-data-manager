import os
import time
import uvicorn
from stock.stock_data_manager import StockDataManager
from api.server import app
from api.deps import PriceCache

if __name__ == "__main__":
    mgr = StockDataManager()
    mgr.start_downloader_agent()
    app.state.cache = PriceCache(mgr)
    app.state.start_time = time.time()
    app.state.uptime = lambda: int(time.time() - app.state.start_time)
    uvicorn.run(
        app,
        host=os.getenv("BIND", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
    )
