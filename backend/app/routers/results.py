from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.config import settings

router = APIRouter(tags=["results"])

@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "status": job.status, "message": "Processing not complete"},
        )
    indicators = (
        db.query(Indicator)
        .filter(Indicator.query_id == job.query_id)
        .options(joinedload(Indicator.metric_values))
        .all()
    )
    output = []
    for ind in indicators:
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
                for mv in ind.metric_values
            ],
        })
    return {
        "job_id": job_id,
        "analyzed_at": job.completed_at.isoformat() if job.completed_at else None,
        "indicators": output,
    }


@router.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: int):
    from app.services.minio_service import get_minio_client
    client = get_minio_client()
    key = f"reports/job_{job_id}.pdf"
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": key},
        ExpiresIn=3600,
    )
    return RedirectResponse(url=url)
