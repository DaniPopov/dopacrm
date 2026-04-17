"""Celery beat tasks for the Subscriptions lifecycle.

Two nightly jobs that keep the commercial data consistent without any
manual staff intervention:

- ``auto_unfreeze_due_subscriptions`` — flips frozen subs whose
  ``frozen_until`` has arrived/passed back to ``active``, extending
  ``expires_at`` by the frozen duration. Runs at 03:00 Asia/Jerusalem.
- ``auto_expire_due_subscriptions`` — flips active subs whose
  ``expires_at`` is in the past to ``expired`` (NOT cancelled — the
  owner-retention distinction). Runs at 03:05, five minutes after
  unfreeze so a member unfrozen today isn't immediately expired.

Both tasks are idempotent (re-running finds zero new rows), bounded by
the partial indexes on ``subscriptions``, and log a structured count
so Grafana / Flower can alert on anomalies.

Celery runs sync Python. We use ``asyncio.run`` to invoke the async
service method per task — each task gets its own event loop + fresh
session, no shared-state across runs.
"""

from __future__ import annotations

import asyncio
import logging

from app.adapters.storage.postgres.database import async_session_factory
from app.core.celery_app import celery_app
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


async def _run_auto_unfreeze() -> int:
    async with async_session_factory() as session:
        service = SubscriptionService(session)
        return await service.auto_unfreeze_due()


async def _run_auto_expire() -> int:
    async with async_session_factory() as session:
        service = SubscriptionService(session)
        return await service.auto_expire_due()


@celery_app.task(name="subscriptions.auto_unfreeze_due", acks_late=True)
def auto_unfreeze_due_subscriptions() -> int:
    """Flip frozen subs whose frozen_until has passed back to active.

    Returns the count moved so Celery results / Flower can display it.
    Logs ``count=N`` via structlog for Loki alerts.
    """
    count = asyncio.run(_run_auto_unfreeze())
    logger.info("subscriptions.auto_unfreeze_due completed", extra={"count": count})
    return count


@celery_app.task(name="subscriptions.auto_expire_due", acks_late=True)
def auto_expire_due_subscriptions() -> int:
    """Flip active subs past their expires_at to expired.

    Returns the count moved. Paired with the retention dashboard — a
    spike here means staff didn't call their cash-paying members in time.
    """
    count = asyncio.run(_run_auto_expire())
    logger.info("subscriptions.auto_expire_due completed", extra={"count": count})
    return count
