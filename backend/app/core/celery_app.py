from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dopacrm",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jerusalem",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Task routes are added per queue once the worker tasks exist.
# Task routes are added per feature as worker tasks are created.
