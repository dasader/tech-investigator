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

        from app.services.pdf_service import markdown_to_pdf_bytes
        from app.services.minio_service import upload_pdf
        from app.services.email_service import send_completion_email
        from app.models.tech_query import TechQuery

        pdf_bytes = markdown_to_pdf_bytes(report_markdown)
        pdf_url = upload_pdf(job_id, pdf_bytes)

        query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
        if query and query.user_email:
            asyncio.run(send_completion_email(query.user_email, job_id, pdf_url))

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
