"""Integration tests for PaymentRepository — real Postgres.

Covers CRUD + every aggregate the dashboard relies on:
- ``sum_for_range`` (net revenue, refunds subtract automatically)
- ``sum_by_plan_for_range`` (JOIN against subscriptions, drop-ins excluded)
- ``sum_by_method_for_range`` (groups across cash / credit_card / ...)
- ``count_distinct_paying_members`` (ARPM denominator)
- Refund chain reads + tenant isolation
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.payment.repositories import PaymentRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.membership_plan import BillingPeriod, PlanType
from app.domain.entities.subscription import PaymentMethod

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def repo(session) -> PaymentRepository:
    return PaymentRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
def member_repo(session) -> MemberRepository:
    return MemberRepository(session)


@pytest.fixture
def plan_repo(session) -> MembershipPlanRepository:
    return MembershipPlanRepository(session)


@pytest.fixture
def sub_repo(session) -> SubscriptionRepository:
    return SubscriptionRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _mk_tenant(tenant_repo, plan_id):
    return await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


async def _mk_member(member_repo, tenant_id):
    return await member_repo.create(
        tenant_id=tenant_id,
        first_name="A",
        last_name="B",
        phone=f"+972-{uuid4().hex[:9]}",
    )


async def _mk_plan(plan_repo, tenant_id, *, name="Monthly", price=25000):
    plan = await plan_repo.create(
        tenant_id=tenant_id,
        name=name,
        type=PlanType.RECURRING,
        price_cents=price,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    return plan


async def _mk_sub(sub_repo, tenant_id, member_id, plan_id, price):
    return await sub_repo.create(
        tenant_id=tenant_id,
        member_id=member_id,
        plan_id=plan_id,
        price_cents=price,
        currency="ILS",
        started_at=date.today(),
        expires_at=None,
        payment_method=PaymentMethod.CASH,
        created_by=None,
        event_data={},
    )


# ── CRUD ─────────────────────────────────────────────────────────────


async def test_create_payment_basic(repo, tenant_repo, member_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    p = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=25000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )
    assert p.amount_cents == 25000
    assert p.currency == "ILS"
    assert p.is_refund() is False


async def test_find_by_id(repo, tenant_repo, member_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    created = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id


async def test_list_for_tenant_isolation(repo, tenant_repo, member_repo, default_plan_id) -> None:
    t1 = await _mk_tenant(tenant_repo, default_plan_id)
    t2 = await _mk_tenant(tenant_repo, default_plan_id)
    m1 = await _mk_member(member_repo, t1.id)
    m2 = await _mk_member(member_repo, t2.id)
    await repo.create(
        tenant_id=t1.id,
        member_id=m1.id,
        amount_cents=1000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )
    await repo.create(
        tenant_id=t2.id,
        member_id=m2.id,
        amount_cents=2000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )

    t1_only = await repo.list_for_tenant(t1.id)
    assert len(t1_only) == 1
    assert t1_only[0].member_id == m1.id


async def test_list_filters_by_member_subscription_method_range(
    repo, tenant_repo, member_repo, plan_repo, sub_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    plan = await _mk_plan(plan_repo, t.id)
    m1 = await _mk_member(member_repo, t.id)
    m2 = await _mk_member(member_repo, t.id)
    s1 = await _mk_sub(sub_repo, t.id, m1.id, plan.id, plan.price_cents)
    s2 = await _mk_sub(sub_repo, t.id, m2.id, plan.id, plan.price_cents)

    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        subscription_id=s1.id,
        amount_cents=25000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m2.id,
        subscription_id=s2.id,
        amount_cents=25000,
        currency="ILS",
        payment_method=PaymentMethod.CREDIT_CARD,
        paid_at=yesterday,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        subscription_id=None,  # drop-in
        amount_cents=5000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=week_ago,
    )

    by_member = await repo.list_for_tenant(t.id, member_id=m1.id)
    assert {p.amount_cents for p in by_member} == {25000, 5000}

    by_sub = await repo.list_for_tenant(t.id, subscription_id=s1.id)
    assert len(by_sub) == 1

    by_method = await repo.list_for_tenant(t.id, method=PaymentMethod.CREDIT_CARD)
    assert len(by_method) == 1

    by_range = await repo.list_for_tenant(t.id, paid_from=yesterday, paid_to=today)
    assert len(by_range) == 2  # excludes the week-ago drop-in


async def test_list_excludes_refunds_when_requested(
    repo, tenant_repo, member_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    original = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=-5000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
        refund_of_payment_id=original.id,
    )

    with_refunds = await repo.list_for_tenant(t.id)
    assert len(with_refunds) == 2

    without_refunds = await repo.list_for_tenant(t.id, include_refunds=False)
    assert len(without_refunds) == 1
    assert without_refunds[0].id == original.id


# ── Refund chain ─────────────────────────────────────────────────────


async def test_list_refunds_for_returns_oldest_first(
    repo, tenant_repo, member_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    original = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
    )

    r1 = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=-3000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
        refund_of_payment_id=original.id,
    )
    # Commit between inserts so created_at advances (within-txn now() freezes).
    await repo._session.commit()  # noqa: SLF001 — test-only timing hint

    r2 = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=-2000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date.today(),
        refund_of_payment_id=original.id,
    )
    await repo._session.commit()  # noqa: SLF001

    chain = await repo.list_refunds_for(original.id)
    assert [r.id for r in chain] == [r1.id, r2.id]


# ── Aggregates ───────────────────────────────────────────────────────


async def test_sum_for_range_includes_refunds_as_negative(
    repo, tenant_repo, member_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    today = date.today()

    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    original = await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=20000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=-5000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
        refund_of_payment_id=original.id,
    )

    total = await repo.sum_for_range(t.id, paid_from=today, paid_to=today)
    assert total == 25000  # 10000 + 20000 - 5000


async def test_sum_for_range_zero_when_no_payments(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    today = date.today()
    assert await repo.sum_for_range(t.id, paid_from=today, paid_to=today) == 0


async def test_sum_by_plan_groups_correctly_and_excludes_drop_ins(
    repo, tenant_repo, member_repo, plan_repo, sub_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    monthly = await _mk_plan(plan_repo, t.id, name="Monthly", price=25000)
    quarterly = await _mk_plan(plan_repo, t.id, name="Quarterly", price=70000)
    m1 = await _mk_member(member_repo, t.id)
    m2 = await _mk_member(member_repo, t.id)
    s_monthly = await _mk_sub(sub_repo, t.id, m1.id, monthly.id, monthly.price_cents)
    s_quarterly = await _mk_sub(sub_repo, t.id, m2.id, quarterly.id, quarterly.price_cents)

    today = date.today()
    # Two months of monthly = 50000, one quarter = 70000, drop-in = 5000.
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        subscription_id=s_monthly.id,
        amount_cents=25000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        subscription_id=s_monthly.id,
        amount_cents=25000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m2.id,
        subscription_id=s_quarterly.id,
        amount_cents=70000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        subscription_id=None,
        amount_cents=5000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )

    rows = await repo.sum_by_plan_for_range(t.id, paid_from=today, paid_to=today)
    by_plan = {row.plan_id: row.cents for row in rows}
    assert by_plan[monthly.id] == 50000
    assert by_plan[quarterly.id] == 70000
    assert sum(by_plan.values()) == 120000  # drop-in excluded


async def test_sum_by_method_groups(repo, tenant_repo, member_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m = await _mk_member(member_repo, t.id)
    today = date.today()

    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=15000,
        currency="ILS",
        payment_method=PaymentMethod.CREDIT_CARD,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m.id,
        amount_cents=20000,
        currency="ILS",
        payment_method=PaymentMethod.CREDIT_CARD,
        paid_at=today,
    )

    by_method = await repo.sum_by_method_for_range(t.id, paid_from=today, paid_to=today)
    assert by_method["cash"] == 10000
    assert by_method["credit_card"] == 35000


async def test_count_distinct_paying_members(
    repo, tenant_repo, member_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    m1 = await _mk_member(member_repo, t.id)
    m2 = await _mk_member(member_repo, t.id)
    today = date.today()

    # m1 has 2 payments, m2 has 1 — distinct members = 2.
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        amount_cents=10000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m1.id,
        amount_cents=5000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )
    await repo.create(
        tenant_id=t.id,
        member_id=m2.id,
        amount_cents=20000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=today,
    )

    n = await repo.count_distinct_paying_members(t.id, paid_from=today, paid_to=today)
    assert n == 2
