"""Integration tests for GymClassRepository — real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.gym_class import GymClass
from app.domain.exceptions import GymClassAlreadyExistsError


@pytest.fixture
def repo(session) -> GymClassRepository:
    return GymClassRepository(session)


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


async def test_create_class_returns_domain_entity(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    cls = await repo.create(
        tenant_id=tenant.id,
        name="Spinning",
        description="High-intensity",
        color="#3B82F6",
    )
    assert isinstance(cls, GymClass)
    assert cls.tenant_id == tenant.id
    assert cls.name == "Spinning"
    assert cls.is_active is True


async def test_create_duplicate_name_same_tenant_raises(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=tenant.id, name="Yoga")
    with pytest.raises(GymClassAlreadyExistsError):
        await repo.create(tenant_id=tenant.id, name="Yoga")


async def test_same_name_allowed_across_tenants(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    """Two gyms can both have a 'Yoga' class — UNIQUE is (tenant_id, name)."""
    tenant_a = await _create_tenant(tenant_repo, default_plan_id)
    tenant_b = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=tenant_a.id, name="Yoga")
    cls_b = await repo.create(tenant_id=tenant_b.id, name="Yoga")
    assert cls_b.tenant_id == tenant_b.id


# ── Find ──────────────────────────────────────────────────────────────────────


async def test_find_by_id(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    created = await repo.create(tenant_id=tenant.id, name="Pilates")
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id


async def test_find_by_id_not_found(repo: GymClassRepository) -> None:
    assert await repo.find_by_id(uuid4()) is None


async def test_find_by_tenant_and_name(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=tenant.id, name="CrossFit")
    found = await repo.find_by_tenant_and_name(tenant.id, "CrossFit")
    assert found is not None
    assert found.name == "CrossFit"


# ── List + active filter ──────────────────────────────────────────────────────


async def test_list_scoped_to_tenant(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant_a = await _create_tenant(tenant_repo, default_plan_id)
    tenant_b = await _create_tenant(tenant_repo, default_plan_id)
    for name in ("Spinning", "Yoga", "Pilates"):
        await repo.create(tenant_id=tenant_a.id, name=name)
    await repo.create(tenant_id=tenant_b.id, name="CrossFit")
    classes = await repo.list_for_tenant(tenant_a.id)
    assert len(classes) == 3
    assert all(c.tenant_id == tenant_a.id for c in classes)


async def test_list_excludes_inactive_by_default(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    active = await repo.create(tenant_id=tenant.id, name="Spinning")
    inactive = await repo.create(tenant_id=tenant.id, name="Yoga")
    await repo.update(inactive.id, is_active=False)

    visible = await repo.list_for_tenant(tenant.id)
    assert len(visible) == 1
    assert visible[0].id == active.id

    all_of_them = await repo.list_for_tenant(tenant.id, include_inactive=True)
    assert len(all_of_them) == 2


async def test_list_orders_alphabetically_by_name(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    for name in ("Yoga", "Crossfit", "Aerobics"):
        await repo.create(tenant_id=tenant.id, name=name)
    results = await repo.list_for_tenant(tenant.id)
    assert [c.name for c in results] == ["Aerobics", "Crossfit", "Yoga"]


# ── Count ─────────────────────────────────────────────────────────────────────


async def test_count_for_tenant(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    for name in ("A", "B", "C"):
        await repo.create(tenant_id=tenant.id, name=name)
    inactive = await repo.create(tenant_id=tenant.id, name="D")
    await repo.update(inactive.id, is_active=False)

    assert await repo.count_for_tenant(tenant.id) == 3
    assert await repo.count_for_tenant(tenant.id, include_inactive=True) == 4


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_renames_class(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    cls = await repo.create(tenant_id=tenant.id, name="OldName")
    updated = await repo.update(cls.id, name="NewName")
    assert updated.name == "NewName"


async def test_update_to_colliding_name_raises(
    repo: GymClassRepository, tenant_repo: TenantRepository, default_plan_id
) -> None:
    """Renaming to a name another class in the same tenant uses → 409."""
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=tenant.id, name="Yoga")
    other = await repo.create(tenant_id=tenant.id, name="Pilates")
    with pytest.raises(GymClassAlreadyExistsError):
        await repo.update(other.id, name="Yoga")
