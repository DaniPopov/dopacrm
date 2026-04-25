from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dopacrm",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # Import task modules here so beat + workers register them.
        "app.workers.subscription_tasks",
        "app.workers.schedule_tasks",
    ],
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

# Beat schedule — nightly Subscriptions lifecycle jobs.
# Crontab entries (not timedelta) so restarts don't shift the clock.
celery_app.conf.beat_schedule = {
    "subscriptions-auto-unfreeze-due": {
        "task": "subscriptions.auto_unfreeze_due",
        "schedule": crontab(hour=3, minute=0),
    },
    "subscriptions-auto-expire-due": {
        # Runs 5 minutes after auto-unfreeze so a sub that just unfroze
        # today isn't immediately re-expired. (Unfreeze extends expires_at
        # past today, but we order the jobs defensively.)
        "task": "subscriptions.auto_expire_due",
        "schedule": crontab(hour=3, minute=5),
    },
    "schedule-extend-horizon": {
        # Nightly at 02:00 — keeps every active template's
        # materialized horizon at ~8 weeks ahead. Idempotent.
        "task": "schedule.extend_horizon",
        "schedule": crontab(hour=2, minute=0),
    },
}
