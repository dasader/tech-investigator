from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, func
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("tech_queries.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending/running/done/failed
    progress_pct = Column(Float, default=0.0)
    current_step = Column(String(100), nullable=True)
    report_markdown = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
