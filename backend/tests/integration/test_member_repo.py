"""Integration tests for MemberRepository — real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.member import Member, MemberStatus
from app.domain.exceptions import MemberAlreadyExistsError


@pytest.fixture
def repo(session) -> MemberRepository:
    return MemberRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None, "default saas plan must be seeded for tests"
    return plan.id


async def _create_tenant(tenant_repo: TenantRepository, plan_id):
    return await tenant_repo.create(
        slug=f"test-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_member_returns_domain_entity(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    member = await repo.create(
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-123-4567",
        email="dana@example.com",
    )
    assert isinstance(member, Member)
    assert member.tenant_id == tenant.id
    assert member.first_name == "Dana"
    assert member.phone == "+972-50-123-4567"
    assert member.status == MemberStatus.ACTIVE
    assert member.custom_fields == {}


async def test_create_member_persists_custom_fields(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    member = await repo.create(
        tenant_id=tenant.id,
        first_name="Yossi",
        last_name="Levi",
        phone="+972-52-111-2222",
        custom_fields={"belt_color": "blue", "is_veteran": True},
    )
    assert member.custom_fields == {"belt_color": "blue", "is_veteran": True}


async def test_create_duplicate_phone_same_tenant_raises(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-123-4567",
    )
    with pytest.raises(MemberAlreadyExistsError):
        await repo.create(
            tenant_id=tenant.id,
            first_name="Other",
            last_name="Person",
            phone="+972-50-123-4567",
        )


async def test_same_phone_allowed_across_tenants(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    """A person can be a member of two gyms with the same phone."""
    tenant_a = await _create_tenant(tenant_repo, default_plan_id)
    tenant_b = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=tenant_a.id,
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-SAME-NUM",
    )
    m_b = await repo.create(
        tenant_id=tenant_b.id,
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-SAME-NUM",
    )
    assert m_b.tenant_id == tenant_b.id


# ── Find ──────────────────────────────────────────────────────────────────────


async def test_find_by_id(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    created = await repo.create(
        tenant_id=tenant.id,
        first_name="Find",
        last_name="Me",
        phone="+972-50-000-0001",
    )
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id


async def test_find_by_id_not_found(repo: MemberRepository) -> None:
    assert await repo.find_by_id(uuid4()) is None


async def test_find_by_tenant_and_phone(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=tenant.id,
        first_name="Phone",
        last_name="Lookup",
        phone="+972-50-PHONE",
    )
    found = await repo.find_by_tenant_and_phone(tenant.id, "+972-50-PHONE")
    assert found is not None
    assert found.first_name == "Phone"


# ── List + filter ─────────────────────────────────────────────────────────────


async def test_list_scoped_to_tenant(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant_a = await _create_tenant(tenant_repo, default_plan_id)
    tenant_b = await _create_tenant(tenant_repo, default_plan_id)
    for i in range(3):
        await repo.create(
            tenant_id=tenant_a.id,
            first_name=f"A{i}",
            last_name="Smith",
            phone=f"+972-50-A-{i}",
        )
    await repo.create(
        tenant_id=tenant_b.id,
        first_name="B",
        last_name="Jones",
        phone="+972-50-B-1",
    )
    members = await repo.list_for_tenant(tenant_a.id)
    assert len(members) == 3
    assert all(m.tenant_id == tenant_a.id for m in members)


async def test_list_filter_by_status(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    active = await repo.create(
        tenant_id=tenant.id,
        first_name="Active",
        last_name="One",
        phone="+972-50-active",
    )
    frozen = await repo.create(
        tenant_id=tenant.id,
        first_name="Frozen",
        last_name="One",
        phone="+972-50-frozen",
    )
    await repo.update(frozen.id, status=MemberStatus.FROZEN)

    results = await repo.list_for_tenant(tenant.id, status=[MemberStatus.ACTIVE])
    assert len(results) == 1
    assert results[0].id == active.id


async def test_list_search_by_name_case_insensitive(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-dana",
    )
    await repo.create(
        tenant_id=tenant.id,
        first_name="Yossi",
        last_name="Levi",
        phone="+972-50-yossi",
    )
    results = await repo.list_for_tenant(tenant.id, search="COHEN")
    assert len(results) == 1
    assert results[0].first_name == "Dana"


# ── Count ─────────────────────────────────────────────────────────────────────


async def test_count_for_tenant(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    for i in range(4):
        await repo.create(
            tenant_id=tenant.id,
            first_name=f"M{i}",
            last_name="X",
            phone=f"+972-50-count-{i}",
        )
    assert await repo.count_for_tenant(tenant.id) == 4
    assert await repo.count_for_tenant(tenant.id, status=MemberStatus.ACTIVE) == 4
    assert await repo.count_for_tenant(tenant.id, status=MemberStatus.FROZEN) == 0


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_status_accepts_enum(
    repo: MemberRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    m = await repo.create(tenant_id=tenant.id, first_name="S", last_name="T", phone="+972-50-upd")
    updated = await repo.update(m.id, status=MemberStatus.FROZEN)
    assert updated.status == MemberStatus.FROZEN
