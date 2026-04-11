"""Integration tests for TenantRepository — real Postgres.

Every test that creates a tenant needs the default SaaS plan (seeded by
migration 0003) because ``tenants.saas_plan_id`` is NOT NULL. The
``default_plan_id`` fixture fetches it once per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import (
    TenantAlreadyExistsError,
    TenantRepository,
)
from app.domain.entities.tenant import Tenant, TenantStatus


@pytest.fixture
def repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None, "default saas plan must be seeded for tests"
    return plan.id


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_tenant_returns_domain_entity(repo: TenantRepository, default_plan_id) -> None:
    tenant = await repo.create(
        slug="ironfit-tlv",
        name="IronFit Tel Aviv",
        saas_plan_id=default_plan_id,
    )
    assert isinstance(tenant, Tenant)
    assert tenant.slug == "ironfit-tlv"
    assert tenant.name == "IronFit Tel Aviv"
    assert tenant.status == TenantStatus.ACTIVE
    assert tenant.saas_plan_id == default_plan_id
    assert tenant.timezone == "Asia/Jerusalem"
    assert tenant.currency == "ILS"
    assert tenant.locale == "he-IL"
    assert tenant.address_country == "IL"
    assert tenant.id is not None


async def test_create_tenant_with_full_fields(repo: TenantRepository, default_plan_id) -> None:
    tenant = await repo.create(
        slug="full-gym",
        name="Full Gym",
        saas_plan_id=default_plan_id,
        phone="+972-3-555-1234",
        logo_url="https://example.com/logo.png",
        email="info@fullgym.co.il",
        website="https://fullgym.co.il",
        address_street="Rothschild 1",
        address_city="Tel Aviv",
        address_postal_code="6578901",
        legal_name="Full Gym Ltd",
        tax_id="123456789",
    )
    assert tenant.phone == "+972-3-555-1234"
    assert tenant.logo_url == "https://example.com/logo.png"
    assert tenant.email == "info@fullgym.co.il"
    assert tenant.website == "https://fullgym.co.il"
    assert tenant.address_street == "Rothschild 1"
    assert tenant.address_city == "Tel Aviv"
    assert tenant.address_country == "IL"
    assert tenant.address_postal_code == "6578901"
    assert tenant.legal_name == "Full Gym Ltd"
    assert tenant.tax_id == "123456789"


async def test_create_tenant_with_custom_regional(repo: TenantRepository, default_plan_id) -> None:
    tenant = await repo.create(
        slug="muscle-beach",
        name="Muscle Beach LA",
        saas_plan_id=default_plan_id,
        phone="+1-310-555-0000",
        timezone="America/Los_Angeles",
        currency="USD",
        locale="en-US",
    )
    assert tenant.timezone == "America/Los_Angeles"
    assert tenant.currency == "USD"
    assert tenant.locale == "en-US"
    assert tenant.phone == "+1-310-555-0000"


async def test_create_duplicate_slug_raises(repo: TenantRepository, default_plan_id) -> None:
    await repo.create(slug="dupe-gym", name="First", saas_plan_id=default_plan_id)
    with pytest.raises(TenantAlreadyExistsError):
        await repo.create(slug="dupe-gym", name="Second", saas_plan_id=default_plan_id)


# ── Find ──────────────────────────────────────────────────────────────────────


async def test_find_by_id(repo: TenantRepository, default_plan_id) -> None:
    created = await repo.create(slug="find-me", name="FindMe Gym", saas_plan_id=default_plan_id)
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.slug == "find-me"


async def test_find_by_id_not_found(repo: TenantRepository) -> None:
    result = await repo.find_by_id(uuid4())
    assert result is None


async def test_find_by_slug(repo: TenantRepository, default_plan_id) -> None:
    await repo.create(slug="slug-gym", name="Slug Gym", saas_plan_id=default_plan_id)
    found = await repo.find_by_slug("slug-gym")
    assert found is not None
    assert found.name == "Slug Gym"


async def test_find_by_slug_not_found(repo: TenantRepository) -> None:
    result = await repo.find_by_slug("nonexistent")
    assert result is None


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_all(repo: TenantRepository, default_plan_id) -> None:
    for i in range(3):
        await repo.create(slug=f"gym-{i}", name=f"Gym {i}", saas_plan_id=default_plan_id)
    tenants = await repo.list_all(limit=10, offset=0)
    assert len(tenants) >= 3


async def test_list_all_pagination(repo: TenantRepository, default_plan_id) -> None:
    for i in range(5):
        await repo.create(slug=f"page-{i}", name=f"Page {i}", saas_plan_id=default_plan_id)
    page1 = await repo.list_all(limit=2, offset=0)
    page2 = await repo.list_all(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_tenant(repo: TenantRepository, default_plan_id) -> None:
    tenant = await repo.create(slug="update-me", name="Old Name", saas_plan_id=default_plan_id)
    updated = await repo.update(tenant.id, name="New Name")
    assert updated.name == "New Name"
    assert updated.slug == "update-me"  # unchanged


async def test_update_status(repo: TenantRepository, default_plan_id) -> None:
    tenant = await repo.create(slug="suspend-me", name="Suspend Me", saas_plan_id=default_plan_id)
    assert tenant.status == TenantStatus.ACTIVE
    updated = await repo.update(tenant.id, status="suspended")
    assert updated.status == TenantStatus.SUSPENDED
