from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

SearchSource = Literal["combined", "scopus"]


class TechQueryCreate(BaseModel):
    category: str
    description: str
    user_email: Optional[str] = None
    search_source: SearchSource = "combined"


class TechQueryOut(BaseModel):
    id: int
    category: str
    description: str
    search_source: str
    created_at: datetime

    class Config:
        from_attributes = True
