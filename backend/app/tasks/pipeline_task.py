import asyncio
from datetime import datetime, timezone
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.job import Job

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline_task(self, job_id: int):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "running"
        db.commit()

        from app.agents.pipeline import run_pipeline
        report_markdown = asyncio.run(run_pipeline(job_id, db))  # used in Task 11 PDF integration

        job.status = "done"
        job.progress_pct = 100.0
        job.current_step = "완료"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"job_id": job_id, "status": "done"}

    except Exception as exc:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = f"오류: {str(exc)[:100]}"
            db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()
