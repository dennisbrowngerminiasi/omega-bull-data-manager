import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Header
from api.models import PriceResponse, BatchRequest
from api.deps import PriceCache

app = FastAPI(title="Omega Bull Data API", version="1.0.0")

def auth_guard(authorization: str = Header(default=None)):
    token = os.getenv("AUTH_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": app.state.uptime()}

def _fetch(symbol: str, cache: PriceCache, threshold: int) -> PriceResponse:
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_REQUEST", "message": "symbol is required"},
        )
    data = cache.get_latest(sym)
    if not data:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "SYMBOL_NOT_FOUND", "message": "symbol not found"},
        )
    as_of = datetime.fromisoformat(data["as_of"])
    age = (datetime.now(timezone.utc) - as_of).total_seconds()
    if age > threshold:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "STALE_DATA", "message": "price data is stale"},
        )
    return PriceResponse(
        symbol=sym,
        price=data["price"],
        currency=data.get("currency", "USD"),
        as_of=data["as_of"],
        source=data.get("source"),
    )

@app.get("/v1/price", response_model=PriceResponse)
def get_price(symbol: str, _: None = Depends(auth_guard)):
    cache: PriceCache = app.state.cache
    threshold = int(os.getenv("STALE_THRESHOLD_SECONDS", "120"))
    try:
        return _fetch(symbol, cache, threshold)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "INTERNAL_ERROR", "message": "internal error"},
        )

@app.post("/v1/prices")
def get_prices(body: BatchRequest, _: None = Depends(auth_guard)):
    cache: PriceCache = app.state.cache
    threshold = int(os.getenv("STALE_THRESHOLD_SECONDS", "120"))
    results = []
    for sym in body.symbols[:1000]:
        try:
            resp = _fetch(sym, cache, threshold)
            results.append(resp.dict())
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
            results.append(
                PriceResponse(
                    symbol=sym.strip().upper(),
                    status="error",
                    error_code=detail.get("error_code"),
                    message=detail.get("message"),
                ).dict()
            )
        except Exception:
            results.append(
                PriceResponse(
                    symbol=sym.strip().upper(),
                    status="error",
                    error_code="INTERNAL_ERROR",
                    message="internal error",
                ).dict()
            )
    return {"results": results}
