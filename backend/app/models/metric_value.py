from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from app.database import Base

class MetricValue(Base):
    __tablename__ = "metric_values"

    id = Column(Integer, primary_key=True, index=True)
    indicator_id = Column(Integer, ForeignKey("indicators.id"), nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    year = Column(Integer, nullable=True)
    country = Column(String(100), nullable=True)
    confidence_score = Column(Float, default=0.0)
    paper_title = Column(Text, nullable=True)
    doi = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    quote = Column(Text, nullable=True)
