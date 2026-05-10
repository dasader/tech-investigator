from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base

class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("tech_queries.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    search_keywords = Column(String(500), nullable=True)
    confirmed_by_user = Column(Boolean, default=False)
