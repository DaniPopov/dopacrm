"""Integration tests for CoachRepository — real Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.coach.repositories import CoachRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.domain.entities.coach import Coach, CoachStatus
from app.domain.entities.user import Role


@pytest.fixture
def repo(session) -> CoachRepository:
    return CoachRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
def user_repo(session) -> UserRepository:
    return UserRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None, "default saas plan must be seeded for tests"
    return plan.id


async def _mk_tenant(tenant_repo: TenantRepository, plan_id):
    return await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


async def test_create_basic_coach(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)

    c = await repo.create(
        tenant_id=t.id,
        first_name="דוד",
        last_name="כהן",
        phone="+972-50-123-4567",
        email="david@gym.com",
    )

    assert isinstance(c, Coach)
    assert c.tenant_id == t.id
    assert c.user_id is None
    assert c.status == CoachStatus.ACTIVE
    assert c.custom_attrs == {}
    assert c.full_name == "דוד כהן"


async def test_create_with_user_link(
    repo, tenant_repo, user_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    u = await user_repo.create(
        email=f"coach-{uuid4().hex[:6]}@gym.com",
        password_hash="x",
        role=Role.COACH,
        tenant_id=t.id,
    )

    c = await repo.create(
        tenant_id=t.id,
        first_name="דוד",
        last_name="כהן",
        user_id=u.id,
    )
    assert c.user_id == u.id
    assert c.can_login() is True


async def test_find_by_user_id(repo, tenant_repo, user_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    u = await user_repo.create(
        email=f"c-{uuid4().hex[:6]}@gym.com",
        password_hash="x",
        role=Role.COACH,
        tenant_id=t.id,
    )
    created = await repo.create(
        tenant_id=t.id, first_name="A", last_name="B", user_id=u.id
    )

    found = await repo.find_by_user_id(u.id)
    assert found is not None
    assert found.id == created.id


async def test_freeze_unfreeze_cancel_transitions(
    repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    c = await repo.create(tenant_id=t.id, first_name="A", last_name="B")

    now = datetime.now(UTC)

    frozen = await repo.freeze(c.id, frozen_at=now)
    assert frozen.status == CoachStatus.FROZEN
    assert frozen.frozen_at is not None

    unfrozen = await repo.unfreeze(c.id)
    assert unfrozen.status == CoachStatus.ACTIVE
    assert unfrozen.frozen_at is None

    cancelled = await repo.cancel(c.id, cancelled_at=now)
    assert cancelled.status == CoachStatus.CANCELLED
    assert cancelled.cancelled_at is not None


async def test_list_filters_status(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    active = await repo.create(tenant_id=t.id, first_name="A", last_name="Active")
    frozen = await repo.create(tenant_id=t.id, first_name="B", last_name="Frozen")
    await repo.freeze(frozen.id, frozen_at=datetime.now(UTC))

    all_rows = await repo.list_for_tenant(t.id)
    assert {c.id for c in all_rows} == {active.id, frozen.id}

    actives = await repo.list_for_tenant(t.id, status=[CoachStatus.ACTIVE])
    assert {c.id for c in actives} == {active.id}


async def test_list_search_matches_name_and_phone(
    repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=t.id, first_name="David", last_name="Cohen", phone="0501")
    await repo.create(tenant_id=t.id, first_name="Yoni", last_name="Levi", phone="0502")

    dv = await repo.list_for_tenant(t.id, search="david")
    assert len(dv) == 1
    by_phone = await repo.list_for_tenant(t.id, search="0502")
    assert len(by_phone) == 1 and by_phone[0].first_name == "Yoni"


async def test_cross_tenant_isolation(repo, tenant_repo, default_plan_id) -> None:
    a = await _mk_tenant(tenant_repo, default_plan_id)
    b = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=a.id, first_name="A-Coach", last_name="X")
    await repo.create(tenant_id=b.id, first_name="B-Coach", last_name="Y")

    a_rows = await repo.list_for_tenant(a.id)
    assert [c.first_name for c in a_rows] == ["A-Coach"]
    b_rows = await repo.list_for_tenant(b.id)
    assert [c.first_name for c in b_rows] == ["B-Coach"]
