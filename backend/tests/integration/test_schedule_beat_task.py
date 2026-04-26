"""Integration tests for the schedule.extend_horizon Celery task.

We exercise ``ScheduleService.extend_horizon_for_template`` (the
underlying coroutine the beat task calls) against the test fixture's
session, so we can assert against the same DB state without colliding
with the production async engine cache (separate engine per test
fixture vs the cached engine the worker uses → "Event loop is
closed" on the second invocation).

The ``schedule.extend_horizon`` Celery wrapper itself is a one-line
``asyncio.run`` over the per-template loop in
``app/workers/schedule_tasks.py`` — covered by inspection. The
business behavior (idempotency, inactive-skip, materialization) lives
in the service and is fully tested here.
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.class_schedule_template.repositories import (
    ClassScheduleTemplateRepository,
)
from app.adapters.storage.postgres.class_session.repositories import (
    ClassSessionRepository,
)
from app.adapters.storage.postgres.coach.repositories import CoachRepository
from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.services.schedule_service import ScheduleService


@pytest.fixture
def schedule_service(session) -> ScheduleService:
    return ScheduleService(session)


@pytest.fixture
def tpl_repo(session) -> ClassScheduleTemplateRepository:
    return ClassScheduleTemplateRepository(session)


@pytest.fixture
def sess_repo(session) -> ClassSessionRepository:
    return ClassSessionRepository(session)


@pytest.fixture
def coach_repo(session) -> CoachRepository:
    return CoachRepository(session)


@pytest.fixture
def class_repo(session) -> GymClassRepository:
    return GymClassRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


async def _seed_template(tenant_repo, class_repo, coach_repo, tpl_repo):
    plan = await SaasPlanRepository(tenant_repo._session).find_default()
    t = await tenant_repo.create(slug=f"t-{uuid4().hex[:8]}", name="Gym", saas_plan_id=plan.id)
    cls = await class_repo.create(tenant_id=t.id, name="Boxing")
    c = await coach_repo.create(tenant_id=t.id, first_name="D", last_name="C")
    return await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["sun", "wed"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )


async def test_extend_horizon_creates_sessions(
    schedule_service, tpl_repo, class_repo, coach_repo, tenant_repo
) -> None:
    """First call materializes a healthy horizon for the template."""
    tpl = await _seed_template(tenant_repo, class_repo, coach_repo, tpl_repo)
    created = await schedule_service.extend_horizon_for_template(tpl)
    # 8 weeks × 2 weekdays = ~16 future sessions.
    assert created > 10


async def test_extend_horizon_idempotent(
    schedule_service, tpl_repo, class_repo, coach_repo, tenant_repo
) -> None:
    """Second call with no time elapsed creates ZERO new sessions —
    the partial UNIQUE on (template_id, starts_at) absorbs them."""
    tpl = await _seed_template(tenant_repo, class_repo, coach_repo, tpl_repo)
    first = await schedule_service.extend_horizon_for_template(tpl)
    assert first > 0
    second = await schedule_service.extend_horizon_for_template(tpl)
    assert second == 0


async def test_extend_horizon_skips_inactive_template(
    schedule_service, tpl_repo, class_repo, coach_repo, tenant_repo
) -> None:
    """An inactive template should yield zero new sessions."""
    tpl = await _seed_template(tenant_repo, class_repo, coach_repo, tpl_repo)
    deactivated = await tpl_repo.deactivate(tpl.id)
    assert deactivated is not None and not deactivated.is_active
    created = await schedule_service.extend_horizon_for_template(deactivated)
    assert created == 0
