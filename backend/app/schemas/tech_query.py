from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


class TechQueryCreate(BaseModel):
    category: str
    description: str
    user_email: Optional[str] = None
    search_source: Literal["semantic_scholar", "scopus"] = "semantic_scholar"


class TechQueryOut(BaseModel):
    id: int
    category: str
    description: str
    search_source: str
    created_at: datetime

    class Config:
        from_attributes = True
