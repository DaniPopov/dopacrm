"""Unit tests for MembershipPlan + PlanEntitlement pure logic."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.membership_plan import (
    BillingPeriod,
    MembershipPlan,
    PlanEntitlement,
    PlanType,
    ResetPeriod,
)


def _plan(**overrides) -> MembershipPlan:
    now = datetime.now(UTC)
    base = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Monthly",
        description=None,
        type=PlanType.RECURRING,
        price_cents=25000,
        currency="ILS",
        billing_period=BillingPeriod.MONTHLY,
        duration_days=None,
        is_active=True,
        custom_attrs={},
        entitlements=[],
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return MembershipPlan(**base)


def _entitlement(**overrides) -> PlanEntitlement:
    now = datetime.now(UTC)
    base = dict(
        id=uuid4(),
        plan_id=uuid4(),
        class_id=None,
        quantity=3,
        reset_period=ResetPeriod.WEEKLY,
        created_at=now,
    )
    base.update(overrides)
    return PlanEntitlement(**base)


# ── Plan logic ───────────────────────────────────────────────────────────────


def test_active_plan_can_be_subscribed_to() -> None:
    assert _plan(is_active=True).can_be_subscribed_to() is True


def test_deactivated_plan_cannot_be_subscribed_to() -> None:
    assert _plan(is_active=False).can_be_subscribed_to() is False


def test_zero_entitlements_means_unlimited_any_class() -> None:
    """The simplest default — no rows = unlimited any class."""
    p = _plan(entitlements=[])
    assert p.is_unlimited_any_class() is True


def test_any_entitlements_means_not_unlimited_default() -> None:
    """As soon as a rule exists, the plan is no longer 'default unlimited'."""
    p = _plan(entitlements=[_entitlement()])
    assert p.is_unlimited_any_class() is False


# ── Entitlement logic ────────────────────────────────────────────────────────


def test_unlimited_reset_period_is_unlimited_rule() -> None:
    e = _entitlement(reset_period=ResetPeriod.UNLIMITED, quantity=None)
    assert e.is_unlimited() is True


def test_metered_reset_periods_are_not_unlimited() -> None:
    for rp in (
        ResetPeriod.WEEKLY,
        ResetPeriod.MONTHLY,
        ResetPeriod.BILLING_PERIOD,
        ResetPeriod.NEVER,
    ):
        assert _entitlement(reset_period=rp).is_unlimited() is False


def test_null_class_id_applies_to_any_class() -> None:
    assert _entitlement(class_id=None).applies_to_any_class() is True


def test_specific_class_id_does_not_apply_to_any_class() -> None:
    assert _entitlement(class_id=uuid4()).applies_to_any_class() is False
