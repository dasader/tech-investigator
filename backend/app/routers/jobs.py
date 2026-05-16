from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.schemas.job import JobOut
from app.tasks.pipeline_task import run_pipeline_task

router = APIRouter(tags=["jobs"])

@router.post("/queries/{query_id}/jobs", response_model=JobOut)
def start_job(query_id: int, db: Session = Depends(get_db)):
    confirmed = db.query(Indicator).filter(
        Indicator.query_id == query_id,
        Indicator.confirmed_by_user == True,
    ).count()
    if confirmed == 0:
        raise HTTPException(status_code=400, detail="확정된 지표가 없습니다")
    job = Job(query_id=query_id, status="pending", progress_pct=0.0)
    db.add(job)
    db.commit()
    db.refresh(job)
    run_pipeline_task.delay(job.id)
    return job

@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    queue_position = None
    if job.status == "pending":
        queue_position = db.query(Job).filter(
            Job.status == "pending",
            Job.id < job_id,
        ).count() + 1
    return JobOut.model_validate(job).model_copy(update={"queue_position": queue_position})
