from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue

router = APIRouter(tags=["results"])

@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=202, detail="Processing not complete")
    indicators = db.query(Indicator).filter(Indicator.query_id == job.query_id).all()
    output = []
    for ind in indicators:
        values = db.query(MetricValue).filter(MetricValue.indicator_id == ind.id).all()
        output.append({
            "indicator": {"id": ind.id, "name": ind.name, "unit": ind.unit},
            "metric_values": [
                {
                    "value": mv.value,
                    "unit": mv.unit,
                    "year": mv.year,
                    "country": mv.country,
                    "confidence_score": mv.confidence_score,
                    "paper_title": mv.paper_title,
                    "doi": mv.doi,
                    "source_url": mv.source_url,
                    "quote": mv.quote,
                }
                for mv in values
            ],
        })
    return {
        "job_id": job_id,
        "analyzed_at": job.completed_at.isoformat() if job.completed_at else None,
        "indicators": output,
    }
