from pydantic import BaseModel
from typing import Optional


class IndicatorBase(BaseModel):
    name: str
    unit: Optional[str] = None
    description: Optional[str] = None
    search_keywords: Optional[str] = None


class IndicatorCreate(IndicatorBase):
    pass


class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    search_keywords: Optional[str] = None
    confirmed_by_user: Optional[bool] = None


class IndicatorOut(IndicatorBase):
    id: int
    query_id: int
    confirmed_by_user: bool

    class Config:
        from_attributes = True
