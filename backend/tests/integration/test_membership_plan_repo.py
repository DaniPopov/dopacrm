"""Integration tests for MembershipPlanRepository — real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    EntitlementInput,
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.membership_plan import (
    BillingPeriod,
    MembershipPlan,
    PlanType,
    ResetPeriod,
)
from app.domain.exceptions import MembershipPlanAlreadyExistsError


@pytest.fixture
def repo(session) -> MembershipPlanRepository:
    return MembershipPlanRepository(session)


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


async def _create_tenant(tenant_repo: TenantRepository, plan_id):
    return await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_recurring_plan_without_entitlements_is_unlimited(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    p = await repo.create(
        tenant_id=tenant.id,
        name="Monthly Unlimited",
        type=PlanType.RECURRING,
        price_cents=25000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    assert isinstance(p, MembershipPlan)
    assert p.entitlements == []
    assert p.is_active is True


async def test_create_one_time_plan_requires_duration_days_and_one_time_billing(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    """DB check constraint enforces shape — service validates before but
    we exercise the backstop here."""
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    p = await repo.create(
        tenant_id=tenant.id,
        name="Drop-in",
        type=PlanType.ONE_TIME,
        price_cents=4000,
        currency="ILS",
        billing_period=BillingPeriod.ONE_TIME,
        duration_days=1,
    )
    assert p.type == PlanType.ONE_TIME
    assert p.duration_days == 1


async def test_create_plan_with_entitlements_stores_all_rows(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    class_repo: GymClassRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    group = await class_repo.create(tenant_id=tenant.id, name="Group")
    pt = await class_repo.create(tenant_id=tenant.id, name="PT")
    p = await repo.create(
        tenant_id=tenant.id,
        name="3 group + 1 PT weekly",
        type=PlanType.RECURRING,
        price_cents=45000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        entitlements=[
            EntitlementInput(class_id=group.id, quantity=3, reset_period=ResetPeriod.WEEKLY),
            EntitlementInput(class_id=pt.id, quantity=1, reset_period=ResetPeriod.WEEKLY),
        ],
    )
    assert len(p.entitlements) == 2
    # Stored quantities reflect input
    quantities = sorted(e.quantity for e in p.entitlements if e.quantity is not None)
    assert quantities == [1, 3]


async def test_create_duplicate_name_same_tenant_raises(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=tenant.id,
        name="Monthly",
        type=PlanType.RECURRING,
        price_cents=25000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    with pytest.raises(MembershipPlanAlreadyExistsError):
        await repo.create(
            tenant_id=tenant.id,
            name="Monthly",
            type=PlanType.RECURRING,
            price_cents=30000,
            currency="ILS",
            billing_period=BillingPeriod.MONTHLY,
        )


async def test_same_name_allowed_across_tenants(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    a = await _create_tenant(tenant_repo, default_plan_id)
    b = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=a.id,
        name="Monthly",
        type=PlanType.RECURRING,
        price_cents=25000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    p_b = await repo.create(
        tenant_id=b.id,
        name="Monthly",
        type=PlanType.RECURRING,
        price_cents=30000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    assert p_b.tenant_id == b.id


# ── Find + list ──────────────────────────────────────────────────────────────


async def test_find_by_id_eager_loads_entitlements(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    class_repo: GymClassRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    cls = await class_repo.create(tenant_id=tenant.id, name="Yoga")
    created = await repo.create(
        tenant_id=tenant.id,
        name="Weekly Yoga",
        type=PlanType.RECURRING,
        price_cents=15000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        entitlements=[
            EntitlementInput(class_id=cls.id, quantity=4, reset_period=ResetPeriod.WEEKLY)
        ],
    )
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert len(found.entitlements) == 1
    assert found.entitlements[0].quantity == 4


async def test_list_excludes_inactive_by_default(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    active = await repo.create(
        tenant_id=tenant.id,
        name="A",
        type=PlanType.RECURRING,
        price_cents=1000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    inactive = await repo.create(
        tenant_id=tenant.id,
        name="B",
        type=PlanType.RECURRING,
        price_cents=2000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    await repo.update(inactive.id, is_active=False)

    visible = await repo.list_for_tenant(tenant.id)
    assert len(visible) == 1
    assert visible[0].id == active.id

    all_of = await repo.list_for_tenant(tenant.id, include_inactive=True)
    assert len(all_of) == 2


async def test_list_scoped_to_tenant(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    a = await _create_tenant(tenant_repo, default_plan_id)
    b = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=a.id,
        name="A-plan",
        type=PlanType.RECURRING,
        price_cents=1000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    await repo.create(
        tenant_id=b.id,
        name="B-plan",
        type=PlanType.RECURRING,
        price_cents=1000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    plans = await repo.list_for_tenant(a.id)
    assert len(plans) == 1
    assert plans[0].name == "A-plan"


# ── Update: replaces entitlements atomically ─────────────────────────────────


async def test_update_replaces_entitlements_completely(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    class_repo: GymClassRepository,
    default_plan_id,
) -> None:
    """Passing a new entitlements list replaces all existing rows."""
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    a = await class_repo.create(tenant_id=tenant.id, name="A")
    b = await class_repo.create(tenant_id=tenant.id, name="B")

    plan = await repo.create(
        tenant_id=tenant.id,
        name="P",
        type=PlanType.RECURRING,
        price_cents=5000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        entitlements=[EntitlementInput(class_id=a.id, quantity=5, reset_period=ResetPeriod.WEEKLY)],
    )
    assert len(plan.entitlements) == 1

    updated = await repo.update(
        plan.id,
        entitlements=[
            EntitlementInput(class_id=b.id, quantity=10, reset_period=ResetPeriod.MONTHLY)
        ],
    )
    assert len(updated.entitlements) == 1
    assert updated.entitlements[0].class_id == b.id
    assert updated.entitlements[0].quantity == 10


async def test_update_clears_entitlements_with_empty_list(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    class_repo: GymClassRepository,
    default_plan_id,
) -> None:
    """Empty list clears all rows → plan becomes unlimited any-class."""
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    cls = await class_repo.create(tenant_id=tenant.id, name="Y")
    plan = await repo.create(
        tenant_id=tenant.id,
        name="P",
        type=PlanType.RECURRING,
        price_cents=5000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        entitlements=[
            EntitlementInput(class_id=cls.id, quantity=2, reset_period=ResetPeriod.WEEKLY)
        ],
    )
    updated = await repo.update(plan.id, entitlements=[])
    assert updated.entitlements == []


async def test_update_without_entitlements_arg_leaves_rows_alone(
    repo: MembershipPlanRepository,
    tenant_repo: TenantRepository,
    class_repo: GymClassRepository,
    default_plan_id,
) -> None:
    """Not passing entitlements keeps existing rows."""
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    cls = await class_repo.create(tenant_id=tenant.id, name="Y")
    plan = await repo.create(
        tenant_id=tenant.id,
        name="P",
        type=PlanType.RECURRING,
        price_cents=5000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        entitlements=[
            EntitlementInput(class_id=cls.id, quantity=2, reset_period=ResetPeriod.WEEKLY)
        ],
    )
    updated = await repo.update(plan.id, price_cents=6000)
    assert updated.price_cents == 6000
    assert len(updated.entitlements) == 1  # untouched
