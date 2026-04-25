"""Integration tests for the higher-level ScheduleService flows.

Where ``test_schedule_repos.py`` covers raw CRUD against the DB, this
file covers end-to-end service behavior:

- Re-materialization on template edit: customized + cancelled rows
  stay frozen, plain materialized rows pick up the new template values.
- per_session pay math: the Schedule-on branch counts scheduled
  (non-cancelled) sessions instead of the v1 distinct-entry-days
  approximation.

These are the most important behaviors of the Schedule feature — if
any regress, payroll silently lies. The tests use real Postgres + the
service layer (no FastAPI test client).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.adapters.storage.postgres.class_coach.repositories import (
    ClassCoachRepository,
)
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
from app.core.security import TokenPayload
from app.domain.entities.class_coach import PayModel
from app.domain.entities.class_session import SessionStatus
from app.domain.entities.user import Role
from app.services.coach_service import CoachService
from app.services.schedule_service import ScheduleService


# ── shared fixtures ──────────────────────────────────────────────────


@pytest.fixture
def schedule_service(session) -> ScheduleService:
    return ScheduleService(session)


@pytest.fixture
def coach_service(session) -> CoachService:
    return CoachService(session)


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
def link_repo(session) -> ClassCoachRepository:
    return ClassCoachRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _setup(tenant_repo, class_repo, coach_repo, default_plan_id, session):
    """One tenant with Schedule on, an owner USER row (FK target),
    a class, and a coach."""
    from app.adapters.storage.postgres.user.repositories import UserRepository

    t = await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}", name="Gym", saas_plan_id=default_plan_id
    )
    await tenant_repo.merge_features(t.id, {"schedule": True, "coaches": True})
    cls = await class_repo.create(tenant_id=t.id, name="Boxing")
    c = await coach_repo.create(tenant_id=t.id, first_name="David", last_name="Cohen")
    owner = await UserRepository(session).create(
        email=f"o-{uuid4().hex[:6]}@g.co",
        password_hash="x",
        role=Role.OWNER,
        tenant_id=t.id,
    )
    return t, cls, c, owner.id


def _caller(tenant_id: UUID, owner_id: UUID) -> TokenPayload:
    """Owner token tied to a real users row (FKs require it)."""
    return TokenPayload(
        sub=str(owner_id),
        role=Role.OWNER.value,
        tenant_id=str(tenant_id),
    )


# ── Re-materialization tests ─────────────────────────────────────────


async def test_template_edit_updates_non_customized_future_sessions(
    schedule_service, sess_repo, tenant_repo, class_repo, coach_repo, default_plan_id
) -> None:
    """The core re-materialization promise: editing a template's
    coach updates future non-customized sessions in place."""
    t, cls, c, owner_id = await _setup(tenant_repo, class_repo, coach_repo, default_plan_id, sess_repo._session)
    new_coach = await coach_repo.create(
        tenant_id=t.id, first_name="Yoni", last_name="Levi"
    )
    caller = _caller(t.id, owner_id)

    tpl = await schedule_service.create_template(
        caller=caller,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
    )

    # Sanity — at least one materialized session.
    sessions = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    assert len(sessions) > 0
    assert all(s.head_coach_id == c.id for s in sessions)

    # Edit template: swap to new_coach.
    await schedule_service.update_template(
        caller=caller, template_id=tpl.id, head_coach_id=new_coach.id
    )

    refreshed = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    # Every (non-customized) session should now point at the new coach.
    assert len(refreshed) == len(sessions)
    assert all(s.head_coach_id == new_coach.id for s in refreshed)


async def test_template_edit_preserves_customized_sessions(
    schedule_service, sess_repo, tenant_repo, class_repo, coach_repo, default_plan_id
) -> None:
    """A session the owner manually edited (e.g. cancelled, swapped
    coach) must NOT be rewritten by template edits."""
    t, cls, c, owner_id = await _setup(tenant_repo, class_repo, coach_repo, default_plan_id, sess_repo._session)
    sub_coach = await coach_repo.create(
        tenant_id=t.id, first_name="Sub", last_name="Coach"
    )
    new_template_coach = await coach_repo.create(
        tenant_id=t.id, first_name="Template", last_name="Newhire"
    )
    caller = _caller(t.id, owner_id)

    tpl = await schedule_service.create_template(
        caller=caller,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
    )

    sessions = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    assert len(sessions) >= 2
    # Customize the first session (swap coach + mark customized).
    customized_id = sessions[0].id
    await schedule_service.update_session(
        caller=caller, session_id=customized_id, head_coach_id=sub_coach.id
    )
    # Cancel the second session.
    cancelled_id = sessions[1].id
    await schedule_service.cancel_session(
        caller=caller, session_id=cancelled_id, reason="test"
    )

    # Edit template — change coach.
    await schedule_service.update_template(
        caller=caller, template_id=tpl.id, head_coach_id=new_template_coach.id
    )

    customized = await sess_repo.find_by_id(customized_id)
    assert customized is not None
    assert customized.head_coach_id == sub_coach.id  # NOT new_template_coach
    assert customized.is_customized is True

    cancelled = await sess_repo.find_by_id(cancelled_id)
    assert cancelled is not None
    assert cancelled.status == SessionStatus.CANCELLED
    # Cancelled session's head_coach_id whatever — owner's last word stands.

    # Untouched future sessions should pick up the new coach.
    remaining = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    untouched = [
        s for s in remaining if s.id not in {customized_id, cancelled_id}
    ]
    assert len(untouched) > 0
    assert all(s.head_coach_id == new_template_coach.id for s in untouched)


async def test_template_deactivate_cancels_future_non_customized(
    schedule_service, sess_repo, tenant_repo, class_repo, coach_repo, default_plan_id
) -> None:
    """Deactivating a template should cancel future non-customized
    sessions so the calendar cleans up. Customized sessions stay as-is."""
    t, cls, c, owner_id = await _setup(tenant_repo, class_repo, coach_repo, default_plan_id, sess_repo._session)
    sub_coach = await coach_repo.create(
        tenant_id=t.id, first_name="Sub", last_name="Coach"
    )
    caller = _caller(t.id, owner_id)

    tpl = await schedule_service.create_template(
        caller=caller,
        class_id=cls.id,
        weekdays=["sun"],
        start_time=time(18, 0),
        end_time=time(19, 0),
        head_coach_id=c.id,
    )

    sessions = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    assert len(sessions) >= 2
    customized_id = sessions[0].id
    await schedule_service.update_session(
        caller=caller, session_id=customized_id, head_coach_id=sub_coach.id
    )

    await schedule_service.deactivate_template(caller=caller, template_id=tpl.id)

    # Customized session stays scheduled.
    customized = await sess_repo.find_by_id(customized_id)
    assert customized is not None
    assert customized.status == SessionStatus.SCHEDULED

    # Other future sessions are now cancelled.
    remaining = await sess_repo.list_for_template_future(tpl.id, datetime.now(UTC))
    others = [s for s in remaining if s.id != customized_id]
    assert len(others) > 0
    assert all(s.status == SessionStatus.CANCELLED for s in others)
    assert all(
        s.cancellation_reason == "template deactivated" for s in others
    )


# ── per_session pay math: Schedule-on branch ─────────────────────────


async def test_per_session_pay_uses_scheduled_session_count_when_schedule_on(
    coach_service,
    schedule_service,
    sess_repo,
    link_repo,
    tenant_repo,
    class_repo,
    coach_repo,
    default_plan_id,
) -> None:
    """The post-Schedule-PR per_session math: count(sessions where
    status='scheduled' AND head_coach_id = coach AND class_id = link.class_id
    AND starts_at in range) * pay_amount_cents.

    Verifies a coach gets paid for sessions they were scheduled to
    teach even when no member showed up — the v1 approximation would
    have returned 0 for that case."""
    t, cls, c, owner_id = await _setup(tenant_repo, class_repo, coach_repo, default_plan_id, sess_repo._session)
    caller = _caller(t.id, owner_id)

    # Pay rate: ₪40 per session.
    await link_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.PER_SESSION,
        pay_amount_cents=4000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
    )

    # Three sessions in May: 2 scheduled, 1 cancelled.
    s1 = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 5, 3, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 5, 3, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    s2 = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 5, 10, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 5, 10, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    s3 = await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 5, 17, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 5, 17, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    # Cancel s3.
    await sess_repo.update(
        s3.id,
        status=SessionStatus.CANCELLED,
        cancelled_at=datetime.now(UTC),
    )

    breakdown = await coach_service.earnings_for(
        caller=caller,
        coach_id=c.id,
        from_=date(2026, 5, 1),
        to=date(2026, 5, 31),
    )

    # 2 scheduled sessions × ₪40 = ₪80.
    assert breakdown.total_cents == 8000
    # By-link breakdown: one row, unit_count=2, cents=8000.
    assert len(breakdown.by_link) == 1
    assert breakdown.by_link[0].unit_count == 2
    assert breakdown.by_link[0].cents == 8000


async def test_per_session_pay_falls_back_to_v1_when_schedule_off(
    coach_service,
    link_repo,
    tenant_repo,
    class_repo,
    coach_repo,
    default_plan_id,
    session,
) -> None:
    """Without the Schedule feature on, per_session falls back to the
    v1 'distinct days with ≥1 attributed entry' approximation. With no
    entries, that returns 0 — verifying the branch swap is wired."""
    from app.adapters.storage.postgres.user.repositories import UserRepository

    t = await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}", name="Gym", saas_plan_id=default_plan_id
    )
    # Schedule explicitly OFF (only coaches enabled).
    await tenant_repo.merge_features(t.id, {"coaches": True, "schedule": False})
    cls = await class_repo.create(tenant_id=t.id, name="Boxing")
    c = await coach_repo.create(tenant_id=t.id, first_name="David", last_name="Cohen")
    owner = await UserRepository(session).create(
        email=f"o-{uuid4().hex[:6]}@g.co",
        password_hash="x",
        role=Role.OWNER,
        tenant_id=t.id,
    )
    caller = _caller(t.id, owner.id)

    await link_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.PER_SESSION,
        pay_amount_cents=4000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
    )

    # No sessions, no entries → v1 approximation = 0 distinct days.
    breakdown = await coach_service.earnings_for(
        caller=caller,
        coach_id=c.id,
        from_=date(2026, 5, 1),
        to=date(2026, 5, 31),
    )
    assert breakdown.total_cents == 0
    assert breakdown.by_link[0].unit_count == 0


async def test_per_session_excludes_other_coachs_sessions(
    coach_service,
    sess_repo,
    link_repo,
    tenant_repo,
    class_repo,
    coach_repo,
    default_plan_id,
) -> None:
    """A coach's earnings should only count sessions they were the
    head coach of. A session in the same class taught by someone else
    is invisible to their pay."""
    t, cls, c, owner_id = await _setup(tenant_repo, class_repo, coach_repo, default_plan_id, sess_repo._session)
    other = await coach_repo.create(
        tenant_id=t.id, first_name="Yoni", last_name="Levi"
    )
    caller = _caller(t.id, owner_id)

    await link_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.PER_SESSION,
        pay_amount_cents=5000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
    )

    # c teaches one, other teaches one.
    await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 5, 3, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 5, 3, 16, 0, tzinfo=UTC),
        head_coach_id=c.id,
    )
    await sess_repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        starts_at=datetime(2026, 5, 10, 15, 0, tzinfo=UTC),
        ends_at=datetime(2026, 5, 10, 16, 0, tzinfo=UTC),
        head_coach_id=other.id,
    )

    breakdown = await coach_service.earnings_for(
        caller=caller,
        coach_id=c.id,
        from_=date(2026, 5, 1),
        to=date(2026, 5, 31),
    )
    assert breakdown.total_cents == 5000  # only c's one session
    assert breakdown.by_link[0].unit_count == 1
