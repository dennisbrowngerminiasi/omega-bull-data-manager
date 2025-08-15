from pydantic import BaseModel, Field
from typing import List, Optional


class PriceResponse(BaseModel):
    symbol: str
    price: Optional[float] = None
    currency: Optional[str] = "USD"
    as_of: Optional[str] = None  # ISO-8601
    source: Optional[str] = None
    status: str = Field(default="ok")
    error_code: Optional[str] = None
    message: Optional[str] = None


class BatchRequest(BaseModel):
    symbols: List[str]
