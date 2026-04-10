"""Integration tests for TenantRepository — real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.tenant.repositories import (
    TenantAlreadyExistsError,
    TenantRepository,
)
from app.domain.entities.tenant import Tenant, TenantStatus


@pytest.fixture
def repo(session) -> TenantRepository:
    return TenantRepository(session)


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_tenant_returns_domain_entity(repo: TenantRepository) -> None:
    tenant = await repo.create(slug="ironfit-tlv", name="IronFit Tel Aviv")
    assert isinstance(tenant, Tenant)
    assert tenant.slug == "ironfit-tlv"
    assert tenant.name == "IronFit Tel Aviv"
    assert tenant.status == TenantStatus.ACTIVE
    assert tenant.timezone == "Asia/Jerusalem"
    assert tenant.currency == "ILS"
    assert tenant.locale == "he-IL"
    assert tenant.id is not None


async def test_create_tenant_with_custom_fields(repo: TenantRepository) -> None:
    tenant = await repo.create(
        slug="muscle-beach",
        name="Muscle Beach LA",
        phone="+1-310-555-0000",
        timezone="America/Los_Angeles",
        currency="USD",
        locale="en-US",
    )
    assert tenant.timezone == "America/Los_Angeles"
    assert tenant.currency == "USD"
    assert tenant.locale == "en-US"
    assert tenant.phone == "+1-310-555-0000"


async def test_create_duplicate_slug_raises(repo: TenantRepository) -> None:
    await repo.create(slug="dupe-gym", name="First")
    with pytest.raises(TenantAlreadyExistsError):
        await repo.create(slug="dupe-gym", name="Second")


# ── Find ──────────────────────────────────────────────────────────────────────


async def test_find_by_id(repo: TenantRepository) -> None:
    created = await repo.create(slug="find-me", name="FindMe Gym")
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.slug == "find-me"


async def test_find_by_id_not_found(repo: TenantRepository) -> None:
    result = await repo.find_by_id(uuid4())
    assert result is None


async def test_find_by_slug(repo: TenantRepository) -> None:
    await repo.create(slug="slug-gym", name="Slug Gym")
    found = await repo.find_by_slug("slug-gym")
    assert found is not None
    assert found.name == "Slug Gym"


async def test_find_by_slug_not_found(repo: TenantRepository) -> None:
    result = await repo.find_by_slug("nonexistent")
    assert result is None


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_all(repo: TenantRepository) -> None:
    for i in range(3):
        await repo.create(slug=f"gym-{i}", name=f"Gym {i}")
    tenants = await repo.list_all(limit=10, offset=0)
    assert len(tenants) >= 3


async def test_list_all_pagination(repo: TenantRepository) -> None:
    for i in range(5):
        await repo.create(slug=f"page-{i}", name=f"Page {i}")
    page1 = await repo.list_all(limit=2, offset=0)
    page2 = await repo.list_all(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_tenant(repo: TenantRepository) -> None:
    tenant = await repo.create(slug="update-me", name="Old Name")
    updated = await repo.update(tenant.id, name="New Name")
    assert updated.name == "New Name"
    assert updated.slug == "update-me"  # unchanged


async def test_update_status(repo: TenantRepository) -> None:
    tenant = await repo.create(slug="suspend-me", name="Suspend Me")
    assert tenant.status == TenantStatus.ACTIVE
    updated = await repo.update(tenant.id, status="suspended")
    assert updated.status == TenantStatus.SUSPENDED
