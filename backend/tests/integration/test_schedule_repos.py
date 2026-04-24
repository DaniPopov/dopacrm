"""Integration tests — schedule_template + session repos.

Covers materialization idempotency, attribution lookup (the hot path
under the new attendance flow), and range scans used by the week view.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
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
from app.domain.entities.class_session import SessionStatus


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
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
def class_repo(session) -> GymClassRepository:
    return GymClassRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _seed(tenant_repo, class_repo, coach_repo, default_plan_id):
    t = await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}", name="Gym", saas_plan_id=default_plan_id
    )
    cls = await class_repo.create(tenant_id=t.id, name="Boxing")
    c = await coach_repo.create(tenant_id=t.id, first_name="D", last_name="C")
    return t, cls, c


# ── Template repo ────────────────────────────────────────────────────


async def test_create_template_roundtrip(
    tpl_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    tpl = await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["sun", "tue"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
        starts_on=date(2026, 1, 1),
    )
    assert tpl.weekdays == ["sun", "tue"]
    assert tpl.is_active is True

    found = await tpl_repo.find_by_id(tpl.id)
    assert found is not None and found.id == tpl.id


async def test_list_for_tenant_only_active(
    tpl_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    active = await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    inactive = await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["mon"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    await tpl_repo.deactivate(inactive.id)

    all_rows = await tpl_repo.list_for_tenant(t.id)
    assert len(all_rows) == 2
    active_rows = await tpl_repo.list_for_tenant(t.id, only_active=True)
    assert {r.id for r in active_rows} == {active.id}


# ── Session repo — materialization ────────────────────────────────────


async def test_materialize_session_idempotent(
    sess_repo, tpl_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    tpl = await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    starts = datetime(2026, 4, 19, 15, 0, tzinfo=UTC)
    ends = datetime(2026, 4, 19, 16, 0, tzinfo=UTC)

    first = await sess_repo.materialize_session(
        tenant_id=t.id,
        class_id=cls.id,
        template_id=tpl.id,
        starts_at=starts,
        ends_at=ends,
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    assert first is not None

    # Second materialization for same (template, starts_at) → no-op.
    second = await sess_repo.materialize_session(
        tenant_id=t.id,
        class_id=cls.id,
        template_id=tpl.id,
        starts_at=starts,
        ends_at=ends,
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    assert second is None


async def test_list_for_range(
    sess_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    # Three sessions — only middle one should match "this week."
    await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 4, 12, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 12, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    mid = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 4, 19, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 26, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )

    rows = await sess_repo.list_for_range(
        t.id,
        from_=datetime(2026, 4, 19, 0, 0, tzinfo=UTC),
        to=datetime(2026, 4, 26, 0, 0, tzinfo=UTC),
    )
    assert [r.id for r in rows] == [mid.id]


# ── Attribution lookup ────────────────────────────────────────────────


async def test_find_active_for_class_tolerance(
    sess_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    s = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )

    # Inside the session → match.
    hit = await sess_repo.find_active_for_class(
        t.id, cls.id, datetime(2026, 4, 19, 18, 30, tzinfo=UTC)
    )
    assert hit is not None and hit.id == s.id

    # 25 min before start → within 30min tolerance → match.
    pre = await sess_repo.find_active_for_class(
        t.id, cls.id, datetime(2026, 4, 19, 17, 35, tzinfo=UTC)
    )
    assert pre is not None and pre.id == s.id

    # 45 min before start → outside tolerance → no match.
    miss = await sess_repo.find_active_for_class(
        t.id, cls.id, datetime(2026, 4, 19, 17, 15, tzinfo=UTC)
    )
    assert miss is None


async def test_find_active_excludes_cancelled(
    sess_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    s = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    await sess_repo.update(
        s.id,
        status=SessionStatus.CANCELLED,
        cancelled_at=datetime.now(UTC),
    )
    hit = await sess_repo.find_active_for_class(
        t.id, cls.id, datetime(2026, 4, 19, 18, 30, tzinfo=UTC)
    )
    assert hit is None


# ── Earnings count ───────────────────────────────────────────────────


async def test_count_scheduled_for_coach(
    sess_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    # Two scheduled + one cancelled in range.
    for i, day in enumerate([12, 19, 26]):
        s = await sess_repo.create(
            tenant_id=t.id,
            class_id=cls.id,
            starts_at=datetime(2026, 4, day, 15, 0, tzinfo=UTC),
            ends_at=datetime(2026, 4, day, 16, 0, tzinfo=UTC),
            head_coach_id=c.id,
        )
        if i == 2:  # cancel the last
            await sess_repo.update(
                s.id,
                status=SessionStatus.CANCELLED,
                cancelled_at=datetime.now(UTC),
            )

    count = await sess_repo.count_scheduled_for_coach(
        tenant_id=t.id,
        coach_id=c.id,
        class_id=cls.id,
        since=datetime(2026, 4, 1, tzinfo=UTC),
        until=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert count == 2  # cancelled excluded


# ── Latest timestamp helper (for beat job) ────────────────────────────


async def test_latest_starts_at_for_template(
    sess_repo, tpl_repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    tpl = await tpl_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    # No sessions yet.
    assert await sess_repo.latest_starts_at_for_template(tpl.id) is None

    latest = datetime(2026, 5, 17, 15, 0, tzinfo=UTC)
    await sess_repo.materialize_session(
        tenant_id=t.id,
        class_id=cls.id,
        template_id=tpl.id,
        starts_at=datetime(2026, 4, 19, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )
    await sess_repo.materialize_session(
        tenant_id=t.id,
        class_id=cls.id,
        template_id=tpl.id,
        starts_at=latest,
        ends_at=latest + timedelta(hours=1),
        head_coach_id=c.id,
        assistant_coach_id=None,
    )

    found = await sess_repo.latest_starts_at_for_template(tpl.id)
    assert found == latest
