"""Integration tests for SaasPlanRepository — real Postgres.

The ``default`` plan is seeded via migration 0003 and preserved by the
test cleanup fixture (it's reference data the dev DB depends on).
Tests read it as-is; they never try to re-create it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.domain.entities.saas_plan import BillingPeriod


@pytest.fixture
def repo(session) -> SaasPlanRepository:
    return SaasPlanRepository(session)


async def test_find_default_returns_seeded_plan(repo: SaasPlanRepository) -> None:
    plan = await repo.find_default()
    assert plan is not None
    assert plan.code == "default"
    assert plan.name == "DopaCRM Standard"
    assert plan.price_cents == 50000
    assert plan.currency == "ILS"
    assert plan.billing_period == BillingPeriod.MONTHLY
    assert plan.max_members == 1000
    assert plan.max_staff_users is None


async def test_find_by_code(repo: SaasPlanRepository) -> None:
    plan = await repo.find_by_code("default")
    assert plan is not None
    assert plan.code == "default"


async def test_find_by_code_not_found(repo: SaasPlanRepository) -> None:
    plan = await repo.find_by_code("nonexistent-plan")
    assert plan is None


async def test_find_by_id(repo: SaasPlanRepository) -> None:
    default = await repo.find_default()
    assert default is not None
    fetched = await repo.find_by_id(default.id)
    assert fetched is not None
    assert fetched.id == default.id
    assert fetched.code == "default"


async def test_find_by_id_not_found(repo: SaasPlanRepository) -> None:
    plan = await repo.find_by_id(uuid4())
    assert plan is None


async def test_list_public(repo: SaasPlanRepository) -> None:
    plans = await repo.list_public()
    assert len(plans) >= 1
    assert any(p.code == "default" for p in plans)
    assert all(p.is_public for p in plans)
