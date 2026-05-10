from celery import Celery
from app.config import settings

celery_app = Celery(
    "techspec",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.pipeline_task"],
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.broker_connection_retry_on_startup = True
