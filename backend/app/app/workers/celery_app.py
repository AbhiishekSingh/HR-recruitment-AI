from celery import Celery

from app.config import settings

celery_app = Celery(
    "resume_screening",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks_ingestion", "app.workers.tasks_matching"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,        # don't lose jobs if a worker dies mid-task
    worker_prefetch_multiplier=1,
)
