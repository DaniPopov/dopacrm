"""Integration tests for ClassEntryRepository — real Postgres.

The important ones are:
- Quota-count accuracy (the feature hinges on this).
- Partial-index-backed queries filter out undone rows.
- Cross-tenant isolation works.
- Day-count aggregate matches what dashboards expect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.class_entry.repositories import (
    ClassEntryRepository,
)
from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.class_entry import OverrideKind
from app.domain.entities.membership_plan import BillingPeriod, PlanType

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(session) -> ClassEntryRepository:
    return ClassEntryRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
def member_repo(session) -> MemberRepository:
    return MemberRepository(session)


@pytest.fixture
def class_repo(session) -> GymClassRepository:
    return GymClassRepository(session)


@pytest.fixture
def plan_repo(session) -> MembershipPlanRepository:
    return MembershipPlanRepository(session)


@pytest.fixture
def sub_repo(session) -> SubscriptionRepository:
    return SubscriptionRepository(session)


@pytest.fixture
async def default_saas_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _setup_world(
    tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
):
    """Spin up tenant + member + class + plan + active subscription."""
    tenant = await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Gym",
        saas_plan_id=default_saas_plan_id,
    )
    member = await member_repo.create(
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Cohen",
        phone=f"05{uuid4().hex[:8]}",
    )
    cls = await class_repo.create(tenant_id=tenant.id, name="Yoga")
    plan = await plan_repo.create(
        tenant_id=tenant.id,
        name="Monthly Yoga",
        type=PlanType.RECURRING,
        price_cents=25000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
    )
    sub = await sub_repo.create(
        tenant_id=tenant.id,
        member_id=member.id,
        plan_id=plan.id,
        price_cents=plan.price_cents,
        currency=plan.currency,
        started_at=datetime(2026, 4, 1, tzinfo=UTC).date(),
        expires_at=None,
        created_by=None,
    )
    return {
        "tenant_id": tenant.id,
        "member_id": member.id,
        "class_id": cls.id,
        "plan_id": plan.id,
        "subscription_id": sub.id,
    }


# ── create ───────────────────────────────────────────────────────────────────


async def test_create_returns_domain_entity_with_entered_at(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    entry = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    assert entry.entered_at is not None
    assert entry.undone_at is None
    assert entry.override is False
    assert entry.is_effective() is True


async def test_create_with_override_marks_the_row(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    entry = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
        override=True,
        override_kind=OverrideKind.QUOTA_EXCEEDED,
        override_reason="birthday class",
    )
    assert entry.override is True
    assert entry.override_kind == OverrideKind.QUOTA_EXCEEDED
    assert entry.override_reason == "birthday class"


# ── count_effective_entries (the quota hot path) ───────────────────────────


async def test_count_effective_entries_for_specific_class(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    # 3 entries for the same class
    for _ in range(3):
        await repo.create(
            tenant_id=world["tenant_id"],
            member_id=world["member_id"],
            subscription_id=world["subscription_id"],
            class_id=world["class_id"],
            entered_by=None,
        )
    since = datetime(2026, 4, 1, tzinfo=UTC)
    count = await repo.count_effective_entries(
        member_id=world["member_id"], class_id=world["class_id"], since=since
    )
    assert count == 3


async def test_count_effective_entries_any_class_wildcard(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    """class_id=None counts across all classes for the member — used for
    the any-class wildcard entitlement."""
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    other_cls = await class_repo.create(tenant_id=world["tenant_id"], name="Spin")

    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=other_cls.id,
        entered_by=None,
    )

    since = datetime(2026, 4, 1, tzinfo=UTC)
    count = await repo.count_effective_entries(
        member_id=world["member_id"], class_id=None, since=since
    )
    assert count == 2


async def test_count_effective_entries_excludes_undone(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    """Undone entries must NOT count toward usage — this is the whole
    point of soft-delete."""
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    e1 = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    # Undo one
    await repo.undo(
        e1.id,
        undone_at=datetime.now(UTC),
        undone_by=None,
        undone_reason="wrong class",
    )

    since = datetime(2026, 4, 1, tzinfo=UTC)
    count = await repo.count_effective_entries(
        member_id=world["member_id"], class_id=world["class_id"], since=since
    )
    assert count == 1


async def test_count_effective_entries_respects_since_cutoff(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    """Only entries with entered_at >= since count — the reset-window boundary."""
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    future_since = datetime.now(UTC) + timedelta(hours=1)
    count = await repo.count_effective_entries(
        member_id=world["member_id"], class_id=world["class_id"], since=future_since
    )
    assert count == 0


# ── undo ────────────────────────────────────────────────────────────────────


async def test_undo_sets_timestamps_and_reason(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    entry = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    undone_at = datetime.now(UTC)
    undone = await repo.undo(
        entry.id,
        undone_at=undone_at,
        undone_by=None,
        undone_reason="oops",
    )
    assert undone.undone_at is not None
    assert undone.undone_reason == "oops"
    assert undone.is_effective() is False


# ── list_for_tenant + filters ──────────────────────────────────────────────


async def test_list_for_tenant_excludes_undone_by_default(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    e1 = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.undo(e1.id, undone_at=datetime.now(UTC), undone_by=None, undone_reason=None)
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    entries = await repo.list_for_tenant(world["tenant_id"])
    assert len(entries) == 1


async def test_list_for_tenant_include_undone(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    e1 = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.undo(e1.id, undone_at=datetime.now(UTC), undone_by=None, undone_reason=None)
    entries = await repo.list_for_tenant(world["tenant_id"], include_undone=True)
    assert len(entries) == 1


async def test_list_for_tenant_undone_only_for_owner_audit(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    """Owner's 'mistakes this week' query."""
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    e2 = await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.undo(e2.id, undone_at=datetime.now(UTC), undone_by=None, undone_reason=None)
    undone_entries = await repo.list_for_tenant(world["tenant_id"], undone_only=True)
    assert len(undone_entries) == 1
    assert undone_entries[0].id == e2.id


async def test_list_for_tenant_override_only(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    """Owner filter for "staff overrides this week"."""
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
        override=True,
        override_kind=OverrideKind.QUOTA_EXCEEDED,
    )
    overrides = await repo.list_for_tenant(world["tenant_id"], override_only=True)
    assert len(overrides) == 1
    assert overrides[0].override is True


async def test_list_scoped_by_tenant(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world_a = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    world_b = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    await repo.create(
        tenant_id=world_a["tenant_id"],
        member_id=world_a["member_id"],
        subscription_id=world_a["subscription_id"],
        class_id=world_a["class_id"],
        entered_by=None,
    )
    await repo.create(
        tenant_id=world_b["tenant_id"],
        member_id=world_b["member_id"],
        subscription_id=world_b["subscription_id"],
        class_id=world_b["class_id"],
        entered_by=None,
    )
    assert len(await repo.list_for_tenant(world_a["tenant_id"])) == 1
    assert len(await repo.list_for_tenant(world_b["tenant_id"])) == 1


# ── count_for_day (dashboard aggregate) ────────────────────────────────────


async def test_count_for_day_includes_only_today_effective_entries(
    repo, tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
) -> None:
    world = await _setup_world(
        tenant_repo, member_repo, class_repo, plan_repo, sub_repo, default_saas_plan_id
    )
    await repo.create(
        tenant_id=world["tenant_id"],
        member_id=world["member_id"],
        subscription_id=world["subscription_id"],
        class_id=world["class_id"],
        entered_by=None,
    )
    today_midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    count = await repo.count_for_day(world["tenant_id"], today_midnight)
    assert count == 1
