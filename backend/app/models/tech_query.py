from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class TechQuery(Base):
    __tablename__ = "tech_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    search_source = Column(String(30), nullable=False, server_default="combined")
    created_at = Column(DateTime, server_default=func.now())
