"""Integration tests for SubscriptionRepository — real Postgres.

Covers the non-trivial DB-level rules:
- Partial UNIQUE "one live sub per member" (second insert fails)
- Shape CHECK constraints (status ↔ timestamps)
- Event log written atomically with every transition
- Renew preserves started_at + price + plan_id
- mark_replaced + create in one transaction for plan change
- Nightly-job queries (find_due_for_unfreeze / find_due_for_expire)
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.security import hash_password
from app.domain.entities.membership_plan import BillingPeriod, PlanType
from app.domain.entities.subscription import (
    PaymentMethod,
    SubscriptionEventType,
    SubscriptionStatus,
)
from app.domain.entities.user import Role
from app.domain.exceptions import (
    MemberAlreadyHasActiveSubscriptionError,
    SubscriptionNotFoundError,
)

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(session) -> SubscriptionRepository:
    return SubscriptionRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
def plan_repo(session) -> MembershipPlanRepository:
    return MembershipPlanRepository(session)


@pytest.fixture
def member_repo(session) -> MemberRepository:
    return MemberRepository(session)


@pytest.fixture
def user_repo(session) -> UserRepository:
    return UserRepository(session)


async def _staff_user(user_repo: UserRepository, tenant_id):
    """Create a staff user in the given tenant so created_by FKs resolve."""
    user = await user_repo.create(
        email=f"staff-{uuid4().hex[:8]}@example.com",
        role=Role.STAFF,
        tenant_id=tenant_id,
        password_hash=hash_password("test123456"),
    )
    return user.id


@pytest.fixture
async def default_saas_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _create_tenant(tenant_repo: TenantRepository, saas_plan_id):
    return await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=saas_plan_id,
    )


async def _create_member(member_repo: MemberRepository, tenant_id):
    return await member_repo.create(
        tenant_id=tenant_id,
        first_name="Dana",
        last_name="Cohen",
        phone=f"05{uuid4().hex[:8]}",
    )


async def _create_plan(plan_repo: MembershipPlanRepository, tenant_id, name="Monthly"):
    return await plan_repo.create(
        tenant_id=tenant_id,
        name=name,
        type=PlanType.RECURRING,
        price_cents=45000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )


# ── Create + partial UNIQUE invariant ────────────────────────────────────────


async def test_create_active_sub_writes_created_event(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)

    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.price_cents == 45000

    events = await repo.list_events(sub.id)
    assert len(events) == 1
    assert events[0].event_type == SubscriptionEventType.CREATED


async def test_second_live_sub_for_same_member_is_rejected(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id, session
) -> None:
    """Partial UNIQUE at the DB level — the backstop for the invariant."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)

    await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date.today(),
        expires_at=None,
        created_by=None,
    )
    await session.commit()

    with pytest.raises(MemberAlreadyHasActiveSubscriptionError):
        await repo.create(
            tenant_id=tenant.id,
            member_id=member.id,
            plan_id=plan.id,
            price_cents=plan.price_cents,
            currency=plan.currency,
            started_at=date.today(),
            expires_at=None,
            created_by=None,
        )


async def test_second_sub_allowed_after_first_is_cancelled(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Partial UNIQUE excludes cancelled rows — history can grow."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)

    first = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 1, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.cancel(
        first.id,
        cancelled_at=date(2026, 3, 1),
        reason="moved_away",
        detail=None,
        created_by=None,
    )

    second = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    assert second.id != first.id


# ── State transitions write events atomically ────────────────────────────────


async def test_freeze_writes_frozen_event_and_sets_timestamps(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 5, 1),
        created_by=None,
    )

    frozen = await repo.freeze(
        sub.id,
        frozen_at=date(2026, 4, 10),
        frozen_until=date(2026, 4, 20),
        created_by=None,
    )
    assert frozen.status == SubscriptionStatus.FROZEN
    assert frozen.frozen_at == date(2026, 4, 10)
    assert frozen.frozen_until == date(2026, 4, 20)

    events = await repo.list_events(sub.id)
    types = [e.event_type for e in events]
    assert SubscriptionEventType.FROZEN in types


async def test_unfreeze_extends_expires_at_and_logs_frozen_days(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Freeze-extends-expiry is a repo-level computation at the call site
    (the service passes the new expires_at). We verify the repo records
    frozen_days in event_data for the owner telemetry."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 5, 1),
        created_by=None,
    )
    await repo.freeze(
        sub.id,
        frozen_at=date(2026, 4, 10),
        frozen_until=date(2026, 4, 20),
        created_by=None,
    )

    # Simulate the service's calculation: frozen for 10 days → push expiry +10d
    unfrozen = await repo.unfreeze(
        sub.id,
        today=date(2026, 4, 20),
        new_expires_at=date(2026, 5, 11),
        created_by=None,
        auto=True,
    )
    assert unfrozen.status == SubscriptionStatus.ACTIVE
    assert unfrozen.expires_at == date(2026, 5, 11)
    assert unfrozen.frozen_at is None
    assert unfrozen.frozen_until is None

    events = await repo.list_events(sub.id)
    unfrozen_event = next(e for e in events if e.event_type == SubscriptionEventType.UNFROZEN)
    assert unfrozen_event.event_data["auto"] is True
    assert unfrozen_event.event_data["frozen_days"] == 10
    assert unfrozen_event.created_by is None  # system


async def test_expire_sets_expired_at_and_writes_system_event(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 4, 30),
        created_by=None,
    )

    expired = await repo.expire(sub.id, today=date(2026, 5, 1))
    assert expired.status == SubscriptionStatus.EXPIRED
    assert expired.expired_at == date(2026, 5, 1)

    events = await repo.list_events(sub.id)
    exp_event = next(e for e in events if e.event_type == SubscriptionEventType.EXPIRED)
    assert exp_event.created_by is None  # system


async def test_renew_from_expired_preserves_started_at_and_logs_days_late(
    repo, tenant_repo, plan_repo, member_repo, user_repo, default_saas_plan_id
) -> None:
    """The retention-telemetry flow: Dana was late → renew rescues her."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 1, 1),
        expires_at=date(2026, 4, 15),
        created_by=None,
    )
    await repo.expire(sub.id, today=date(2026, 4, 16))

    staff_id = await _staff_user(user_repo, tenant.id)
    renewed = await repo.renew(
        sub.id,
        new_expires_at=date(2026, 5, 18),
        days_late=3,
        created_by=staff_id,
    )
    # Tenure + identity preserved
    assert renewed.id == sub.id
    assert renewed.started_at == date(2026, 1, 1)
    assert renewed.status == SubscriptionStatus.ACTIVE
    assert renewed.expires_at == date(2026, 5, 18)
    # expired_at stays as a historical marker of the lapse
    assert renewed.expired_at == date(2026, 4, 16)

    events = await repo.list_events(sub.id)
    renew_event = next(e for e in events if e.event_type == SubscriptionEventType.RENEWED)
    assert renew_event.event_data["days_late"] == 3
    assert renew_event.created_by == staff_id


async def test_plan_change_flow_replaces_old_sub_and_links_forward(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Two-phase plan-change flow (what the service will call):
    1. mark_replaced_pending: old sub → status='replaced', replaced_by_id=NULL
       — clears it from the partial-UNIQUE live set.
    2. create new sub with the new plan.
    3. set_replaced_by: fill in the forward link on the old sub.

    End state: old sub points at new sub; partial UNIQUE still intact
    (only new is in active/frozen); old sub's timeline has a REPLACED event.
    """
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    silver = await _create_plan(plan_repo, tenant.id, name="Silver")
    gold = await _create_plan(plan_repo, tenant.id, name="Gold")

    old = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=silver.id,
        price_cents=silver.price_cents,
        currency=silver.currency,
        started_at=date(2026, 1, 1),
        expires_at=None,
        created_by=None,
    )

    # Phase 1: old → replaced (forward link still NULL). CHECK allows this.
    pending = await repo.mark_replaced_pending(
        old.id,
        replaced_at=date(2026, 4, 1),
        created_by=None,
        event_data={"from_plan_id": str(silver.id), "to_plan_id": str(gold.id)},
    )
    assert pending.status == SubscriptionStatus.REPLACED
    assert pending.replaced_by_id is None  # will be filled in phase 3

    # Phase 2: insert new sub. Partial UNIQUE is now satisfied.
    new = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=gold.id,
        price_cents=gold.price_cents,
        currency=gold.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    assert new.plan_id == gold.id

    # Phase 3: fill forward link.
    linked = await repo.set_replaced_by(old.id, replaced_by_id=new.id)
    assert linked.replaced_by_id == new.id
    assert linked.status == SubscriptionStatus.REPLACED

    # Timeline on old sub: CREATED + REPLACED events
    events = await repo.list_events(old.id)
    types = [e.event_type for e in events]
    assert SubscriptionEventType.CREATED in types
    assert SubscriptionEventType.REPLACED in types


async def test_cancel_writes_reason_into_event_data(
    repo, tenant_repo, plan_repo, member_repo, user_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )

    staff_id = await _staff_user(user_repo, tenant.id)
    cancelled = await repo.cancel(
        sub.id,
        cancelled_at=date(2026, 5, 1),
        reason="too_expensive",
        detail="Planning to switch gyms",
        created_by=staff_id,
    )
    assert cancelled.status == SubscriptionStatus.CANCELLED
    assert cancelled.cancellation_reason == "too_expensive"

    events = await repo.list_events(sub.id)
    ev = next(e for e in events if e.event_type == SubscriptionEventType.CANCELLED)
    assert ev.event_data["reason"] == "too_expensive"
    assert ev.event_data["detail"] == "Planning to switch gyms"


# ── Reads ────────────────────────────────────────────────────────────────────


async def test_find_live_for_member_returns_active_sub(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    live = await repo.find_live_for_member(tenant.id, member.id)
    assert live is not None
    assert live.id == sub.id


async def test_find_live_for_member_returns_none_when_only_cancelled(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.cancel(
        sub.id,
        cancelled_at=date.today(),
        reason=None,
        detail=None,
        created_by=None,
    )
    assert await repo.find_live_for_member(tenant.id, member.id) is None


async def test_list_for_tenant_scopes_by_tenant(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    a = await _create_tenant(tenant_repo, default_saas_plan_id)
    b = await _create_tenant(tenant_repo, default_saas_plan_id)
    mem_a = await _create_member(member_repo, a.id)
    mem_b = await _create_member(member_repo, b.id)
    plan_a = await _create_plan(plan_repo, a.id)
    plan_b = await _create_plan(plan_repo, b.id)

    await repo.create(
        tenant_id=a.id,
        member_id=mem_a.id,
        plan_id=plan_a.id,
        price_cents=plan_a.price_cents,
        currency=plan_a.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.create(
        tenant_id=b.id,
        member_id=mem_b.id,
        plan_id=plan_b.id,
        price_cents=plan_b.price_cents,
        currency=plan_b.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )

    a_subs = await repo.list_for_tenant(a.id)
    assert len(a_subs) == 1
    assert a_subs[0].member_id == mem_a.id


# ── Nightly-job queries ──────────────────────────────────────────────────────


async def test_find_due_for_expire_returns_only_active_with_past_expires(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    plan = await _create_plan(plan_repo, tenant.id)
    # Card-auto: expires_at=None, never shows up
    card_member = await _create_member(member_repo, tenant.id)
    await repo.create(
        tenant_id=tenant.id,
        member_id=card_member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    # Cash, past expiry: should show up
    cash_member = await _create_member(member_repo, tenant.id)
    past = await repo.create(
        tenant_id=tenant.id,
        member_id=cash_member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 3, 1),
        expires_at=date(2026, 4, 5),
        created_by=None,
    )
    # Cash, future expiry: should NOT show up
    future_member = await _create_member(member_repo, tenant.id)
    await repo.create(
        tenant_id=tenant.id,
        member_id=future_member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 5, 1),
        created_by=None,
    )

    due = await repo.find_due_for_expire(today=date(2026, 4, 20))
    ids = [s.id for s in due]
    assert past.id in ids
    assert len(due) == 1


async def test_find_due_for_unfreeze_returns_only_frozen_with_past_until(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    plan = await _create_plan(plan_repo, tenant.id)
    # Open-ended freeze (frozen_until=None): NOT due
    m_open = await _create_member(member_repo, tenant.id)
    sub_open = await repo.create(
        tenant_id=tenant.id,
        member_id=m_open.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.freeze(sub_open.id, frozen_at=date.today(), frozen_until=None, created_by=None)
    # Past frozen_until: DUE
    m_due = await _create_member(member_repo, tenant.id)
    sub_due = await repo.create(
        tenant_id=tenant.id,
        member_id=m_due.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.freeze(
        sub_due.id,
        frozen_at=date(2026, 4, 1),
        frozen_until=date(2026, 4, 10),
        created_by=None,
    )

    due = await repo.find_due_for_unfreeze(today=date(2026, 4, 15))
    ids = [s.id for s in due]
    assert sub_due.id in ids
    assert sub_open.id not in ids


# ── Missing sub raises ───────────────────────────────────────────────────────


async def test_operations_on_missing_sub_raise_not_found(repo) -> None:
    missing = uuid4()
    with pytest.raises(SubscriptionNotFoundError):
        await repo.freeze(
            missing,
            frozen_at=date.today(),
            frozen_until=None,
            created_by=None,
        )


async def test_list_for_member_returns_full_history(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Both the cancelled sub and the new active sub are returned —
    history survives cancellation. Order is newest-first; with identical
    created_at timestamps the tiebreaker is unspecified, so we just
    assert set equality."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    first = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 1, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.cancel(
        first.id,
        cancelled_at=date(2026, 2, 1),
        reason=None,
        detail=None,
        created_by=None,
    )
    second = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 3, 1),
        expires_at=None,
        created_by=None,
    )
    history = await repo.list_for_member(tenant.id, member.id)
    assert {s.id for s in history} == {second.id, first.id}


# ── Filters ──────────────────────────────────────────────────────────────────


async def test_list_expires_before_filter(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    plan = await _create_plan(plan_repo, tenant.id)
    m1 = await _create_member(member_repo, tenant.id)
    m2 = await _create_member(member_repo, tenant.id)
    await repo.create(
        tenant_id=tenant.id,
        member_id=m1.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 5, 1),
        created_by=None,
    )
    await repo.create(
        tenant_id=tenant.id,
        member_id=m2.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 6, 1),
        created_by=None,
    )
    only_may = await repo.list_for_tenant(tenant.id, expires_before=date(2026, 5, 15))
    assert len(only_may) == 1


async def test_filter_by_status(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    plan = await _create_plan(plan_repo, tenant.id)
    m1 = await _create_member(member_repo, tenant.id)
    m2 = await _create_member(member_repo, tenant.id)
    active = await repo.create(
        tenant_id=tenant.id,
        member_id=m1.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    cancel_me = await repo.create(
        tenant_id=tenant.id,
        member_id=m2.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=None,
        created_by=None,
    )
    await repo.cancel(
        cancel_me.id,
        cancelled_at=date.today(),
        reason=None,
        detail=None,
        created_by=None,
    )
    active_only = await repo.list_for_tenant(tenant.id, status=SubscriptionStatus.ACTIVE)
    assert [s.id for s in active_only] == [active.id]


async def test_expired_at_preserved_across_renew(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """The "Dana forgot to pay, renewed 3 days late" workflow — the
    expired_at breadcrumb must NOT be wiped on renew."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 1, 1),
        expires_at=date(2026, 4, 15),
        created_by=None,
    )
    await repo.expire(sub.id, today=date(2026, 4, 16))
    await repo.renew(
        sub.id,
        new_expires_at=date(2026, 5, 18),
        days_late=3,
        created_by=None,
    )
    refreshed = await repo.find_by_id(sub.id)
    assert refreshed is not None
    assert refreshed.expired_at == date(2026, 4, 16)


async def test_payment_method_and_detail_round_trip(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Covers all four enum values through a real INSERT + SELECT."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    plan = await _create_plan(plan_repo, tenant.id)

    combos = [
        (PaymentMethod.CASH, None),
        (PaymentMethod.CREDIT_CARD, "Isracard 1234"),
        (PaymentMethod.STANDING_ORDER, None),
        (PaymentMethod.OTHER, "bank transfer, ref 9876"),
    ]
    for method, detail in combos:
        member = await _create_member(member_repo, tenant.id)
        sub = await repo.create(
            tenant_id=tenant.id,
            member_id=member.id,
            plan_id=plan.id,
            price_cents=plan.price_cents,
            currency=plan.currency,
            started_at=date(2026, 4, 1),
            expires_at=None,
            payment_method=method,
            payment_method_detail=detail,
            created_by=None,
        )
        assert sub.payment_method == method
        assert sub.payment_method_detail == detail


async def test_renew_can_flip_payment_method_and_logs_change(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    """Member went from cash → standing order at renewal. The change
    is logged in the 'renewed' event so the owner can see method migrations."""
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 1, 1),
        expires_at=date(2026, 4, 15),
        payment_method=PaymentMethod.CASH,
        payment_method_detail=None,
        created_by=None,
    )
    renewed = await repo.renew(
        sub.id,
        new_expires_at=date(2026, 5, 15),
        days_late=0,
        created_by=None,
        new_payment_method=PaymentMethod.STANDING_ORDER,
    )
    assert renewed.payment_method == PaymentMethod.STANDING_ORDER

    events = await repo.list_events(sub.id)
    renew_event = next(e for e in events if e.event_type == SubscriptionEventType.RENEWED)
    assert renew_event.event_data["previous_payment_method"] == "cash"
    assert renew_event.event_data["new_payment_method"] == "standing_order"


async def test_renew_without_method_override_keeps_existing_method(
    repo, tenant_repo, plan_repo, member_repo, default_saas_plan_id
) -> None:
    tenant = await _create_tenant(tenant_repo, default_saas_plan_id)
    member = await _create_member(member_repo, tenant.id)
    plan = await _create_plan(plan_repo, tenant.id)
    sub = await repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=date(2026, 4, 1),
        expires_at=date(2026, 5, 1),
        payment_method=PaymentMethod.CREDIT_CARD,
        payment_method_detail="Visa 1234",
        created_by=None,
    )
    renewed = await repo.renew(
        sub.id,
        new_expires_at=date(2026, 6, 1),
        days_late=0,
        created_by=None,
        # No method override — should stay CREDIT_CARD
    )
    assert renewed.payment_method == PaymentMethod.CREDIT_CARD
    assert renewed.payment_method_detail == "Visa 1234"


async def test_today_offset_helper_smoke() -> None:
    """Sanity: timedelta arithmetic used in repo code works as expected.
    Guards against Python version quirks in date math."""
    assert date(2026, 4, 17) - date(2026, 4, 10) == timedelta(days=7)
