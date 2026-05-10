from pydantic import BaseModel
from typing import Optional


class MetricValueOut(BaseModel):
    id: int
    indicator_id: int
    value: Optional[float] = None
    unit: Optional[str] = None
    year: Optional[int] = None
    country: Optional[str] = None
    confidence_score: float
    paper_title: Optional[str] = None
    doi: Optional[str] = None
    source_url: Optional[str] = None
    quote: Optional[str] = None

    class Config:
        from_attributes = True
