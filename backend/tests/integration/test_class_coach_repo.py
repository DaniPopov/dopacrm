"""Integration tests for ClassCoachRepository — real Postgres.

Covers: link CRUD, unique (class, coach, role) collision, attribution
candidate filtering by weekday + status + date window, the earnings
scan helpers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.class_coach.repositories import ClassCoachRepository
from app.adapters.storage.postgres.coach.repositories import CoachRepository
from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.class_coach import PayModel
from app.domain.exceptions import ClassCoachConflictError


@pytest.fixture
def repo(session) -> ClassCoachRepository:
    return ClassCoachRepository(session)


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
    c = await coach_repo.create(
        tenant_id=t.id, first_name="David", last_name="Cohen"
    )
    return t, cls, c


async def test_create_link_roundtrip(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    link = await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.PER_ATTENDANCE,
        pay_amount_cents=5000,
        weekdays=["sun", "tue"],
        starts_on=date(2026, 1, 1),
    )
    assert link.pay_model == PayModel.PER_ATTENDANCE
    assert link.weekdays == ["sun", "tue"]
    assert link.is_primary is True

    found = await repo.find_by_id(link.id)
    assert found is not None
    assert found.id == link.id


async def test_duplicate_role_conflict(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.FIXED,
        pay_amount_cents=300000,
        weekdays=[],
    )
    with pytest.raises(ClassCoachConflictError):
        await repo.create(
            tenant_id=t.id,
            class_id=cls.id,
            coach_id=c.id,
            role="ראשי",
            is_primary=False,
            pay_model=PayModel.FIXED,
            pay_amount_cents=10000,
            weekdays=[],
        )


async def test_same_coach_different_role_allowed(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.FIXED,
        pay_amount_cents=300000,
        weekdays=[],
    )
    # Same coach, different role — allowed.
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="עוזר",
        is_primary=False,
        pay_model=PayModel.PER_SESSION,
        pay_amount_cents=3000,
        weekdays=["sun"],
    )

    rows = await repo.list_for_class(t.id, cls.id)
    assert {r.role for r in rows} == {"ראשי", "עוזר"}


async def test_list_for_class_only_current_hides_ended(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    # Ended row — owner's history, should not show in only_current.
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="past",
        is_primary=False,
        pay_model=PayModel.FIXED,
        pay_amount_cents=100,
        weekdays=[],
        starts_on=date(2024, 1, 1),
        ends_on=date(2024, 12, 31),
    )
    # Current
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="current",
        is_primary=True,
        pay_model=PayModel.FIXED,
        pay_amount_cents=200,
        weekdays=[],
    )
    all_rows = await repo.list_for_class(t.id, cls.id)
    assert {r.role for r in all_rows} == {"past", "current"}

    current_rows = await repo.list_for_class(t.id, cls.id, only_current=True)
    assert {r.role for r in current_rows} == {"current"}


async def test_find_attribution_candidates_weekday_filter(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)
    other = await coach_repo.create(
        tenant_id=t.id, first_name="Yoni", last_name="Levi"
    )

    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="sun-coach",
        is_primary=True,
        pay_model=PayModel.PER_ATTENDANCE,
        pay_amount_cents=5000,
        weekdays=["sun"],
        starts_on=date(2026, 1, 1),
    )
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=other.id,
        role="wed-coach",
        is_primary=True,
        pay_model=PayModel.PER_ATTENDANCE,
        pay_amount_cents=5000,
        weekdays=["wed"],
        starts_on=date(2026, 1, 1),
    )

    # Sunday 2026-04-19 → only sun-coach matches.
    sun = await repo.find_attribution_candidates(t.id, cls.id, date(2026, 4, 19))
    assert [r.role for r in sun] == ["sun-coach"]

    # Wednesday 2026-04-22 → only wed-coach matches.
    wed = await repo.find_attribution_candidates(t.id, cls.id, date(2026, 4, 22))
    assert [r.role for r in wed] == ["wed-coach"]


async def test_attribution_excludes_frozen_coach(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="ראשי",
        is_primary=True,
        pay_model=PayModel.PER_ATTENDANCE,
        pay_amount_cents=5000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
    )
    # Freeze the coach — they should disappear from attribution candidates.
    await coach_repo.freeze(c.id, frozen_at=datetime.now(UTC))

    cands = await repo.find_attribution_candidates(t.id, cls.id, date(2026, 4, 22))
    assert cands == []


async def test_attribution_empty_weekdays_means_always(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="catch-all",
        is_primary=True,
        pay_model=PayModel.FIXED,
        pay_amount_cents=300000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
    )
    for day in range(19, 26):  # Sun 4/19 .. Sat 4/25
        cands = await repo.find_attribution_candidates(t.id, cls.id, date(2026, 4, day))
        assert len(cands) == 1
        assert cands[0].role == "catch-all"


async def test_list_active_links_for_coach_in_range_overlap(
    repo, class_repo, coach_repo, tenant_repo, default_plan_id
) -> None:
    t, cls, c = await _seed(tenant_repo, class_repo, coach_repo, default_plan_id)

    # Rate row Jan–June
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="old-rate",
        is_primary=False,
        pay_model=PayModel.FIXED,
        pay_amount_cents=200000,
        weekdays=[],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 6, 30),
    )
    # Rate row Jul–onwards
    await repo.create(
        tenant_id=t.id,
        class_id=cls.id,
        coach_id=c.id,
        role="new-rate",
        is_primary=True,
        pay_model=PayModel.FIXED,
        pay_amount_cents=300000,
        weekdays=[],
        starts_on=date(2026, 7, 1),
    )

    spring = await repo.list_active_links_for_coach_in_range(
        t.id, c.id, date(2026, 3, 1), date(2026, 5, 1)
    )
    assert {r.role for r in spring} == {"old-rate"}

    summer = await repo.list_active_links_for_coach_in_range(
        t.id, c.id, date(2026, 6, 15), date(2026, 7, 15)
    )
    assert {r.role for r in summer} == {"old-rate", "new-rate"}
