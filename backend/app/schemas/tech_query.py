from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class TechQueryCreate(BaseModel):
    category: str
    description: str
    user_email: Optional[str] = None


class TechQueryOut(BaseModel):
    id: int
    category: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True
