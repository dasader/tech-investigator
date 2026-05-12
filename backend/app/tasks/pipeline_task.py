import asyncio
from datetime import datetime, timezone
from app.celery_app import celery_app
from app.database import SessionLocal

# Worker 시작 시 모든 모델을 임포트해야 SQLAlchemy FK 관계가 정상 초기화됨
import app.models.tech_query   # noqa: F401
import app.models.indicator    # noqa: F401
import app.models.metric_value # noqa: F401
import app.models.job          # noqa: F401
from app.models.job import Job
from app.models.tech_query import TechQuery

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline_task(self, job_id: int):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
        user_email = query.user_email if query else None

        job.status = "running"
        db.commit()

        from app.agents.pipeline import run_pipeline
        report_markdown = asyncio.run(run_pipeline(job_id, db))

        job.status = "done"
        job.progress_pct = 100.0
        job.current_step = "완료"
        job.report_markdown = report_markdown
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        if user_email:
            from app.services.email_service import send_completion_email
            asyncio.run(send_completion_email(user_email, job_id))

        return {"job_id": job_id, "status": "done"}

    except Exception as exc:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = f"오류: {str(exc)[:93]}"
            db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()
