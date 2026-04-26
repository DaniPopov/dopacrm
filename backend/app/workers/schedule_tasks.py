"""Celery beat task — nightly schedule horizon extension.

For every active template across the platform, ensure there's at
least ``DEFAULT_HORIZON_WEEKS`` of materialized future sessions ahead.
Idempotent — re-running creates zero new rows if the horizon is
already covered (the partial UNIQUE index on (template_id, starts_at)
absorbs duplicates).

Runs nightly at 02:00 Asia/Jerusalem. Crontab is set in
``app/core/celery_app.py`` so beat-restart doesn't shift the clock.

Note on tenant feature flags: the beat task DOES extend horizons even
for tenants where Schedule is disabled. Reasoning: if Schedule is
turned off and back on, the owner expects to see existing templates
keep working with no gap. Materialization is cheap (idempotent insert
per missing date) and storage is dominated by historical sessions
anyway. If a real cost concern emerges, add a tenant-level skip here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.adapters.storage.postgres.class_schedule_template.repositories import (
    ClassScheduleTemplateRepository,
)
from app.adapters.storage.postgres.database import async_session_factory
from app.core.celery_app import celery_app
from app.services.schedule_service import (
    ScheduleService,
)

logger = logging.getLogger(__name__)

#: When the latest materialized session for a template is closer than
#: this to today, the beat job extends. Set below the default horizon
#: so the job has slack — typical run leaves ~6 weeks ahead, gets
#: extended to 8.
HORIZON_EXTEND_THRESHOLD = timedelta(weeks=6)


async def _run_extend_horizon() -> dict[str, int]:
    """For each active template, materialize up to DEFAULT_HORIZON_WEEKS
    ahead. Returns ``{templates_processed, sessions_created}``.

    Per-template work is isolated — a failure on one template doesn't
    abort the others. Errors are logged and counted as 0 sessions.
    """
    sessions_created = 0
    templates_processed = 0
    errors = 0

    async with async_session_factory() as session:
        tpl_repo = ClassScheduleTemplateRepository(session)
        templates = await tpl_repo.list_all_active()

        for tpl in templates:
            templates_processed += 1
            try:
                service = ScheduleService(session)
                created = await service.extend_horizon_for_template(tpl)
                # _materialize_horizon doesn't commit (it relies on the
                # service's command commits). Commit explicitly here per
                # template so a single bad template doesn't roll back the
                # rest.
                await session.commit()
                sessions_created += created
            except Exception:  # noqa: BLE001
                errors += 1
                logger.exception(
                    "schedule.beat.template_failed",
                    extra={
                        "tenant_id": str(tpl.tenant_id),
                        "template_id": str(tpl.id),
                    },
                )
                await session.rollback()

    return {
        "templates_processed": templates_processed,
        "sessions_created": sessions_created,
        "errors": errors,
    }


@celery_app.task(name="schedule.extend_horizon")
def extend_schedule_horizon() -> dict[str, int]:
    """Nightly task — entry point invoked by Celery beat."""
    started = datetime.now(UTC)
    result = asyncio.run(_run_extend_horizon())
    duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000

    logger.info(
        "schedule.horizon_extended",
        extra={
            "event": "schedule.horizon_extended",
            "templates_processed": result["templates_processed"],
            "sessions_created": result["sessions_created"],
            "errors": result["errors"],
            "duration_ms": round(duration_ms),
        },
    )
    return result
