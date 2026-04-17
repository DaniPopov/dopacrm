"""Unit tests for Subscription + SubscriptionEvent pure logic.

Covers the state-machine guards (``can_*``), the nightly-job predicates
(``should_auto_*``), and the ``days_late`` calculation used by the
retention telemetry.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from app.domain.entities.subscription import (
    PaymentMethod,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)


def _sub(**overrides) -> Subscription:
    now = datetime.now(UTC)
    base = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        member_id=uuid4(),
        plan_id=uuid4(),
        status=SubscriptionStatus.ACTIVE,
        price_cents=45000,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        payment_method_detail=None,
        started_at=date(2026, 4, 1),
        expires_at=None,
        frozen_at=None,
        frozen_until=None,
        expired_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        replaced_at=None,
        replaced_by_id=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return Subscription(**base)


# ── can_freeze ───────────────────────────────────────────────────────────────


def test_active_sub_can_be_frozen() -> None:
    assert _sub(status=SubscriptionStatus.ACTIVE).can_freeze() is True


def test_frozen_sub_cannot_be_frozen_again() -> None:
    assert _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today()).can_freeze() is False


def test_expired_cancelled_replaced_cannot_be_frozen() -> None:
    # Each terminal/soft-terminal state blocks re-freezing. Build each with
    # its required shape (cancelled needs cancelled_at, replaced needs the pair).
    assert _sub(status=SubscriptionStatus.EXPIRED, expired_at=date.today()).can_freeze() is False
    cancelled = _sub(status=SubscriptionStatus.CANCELLED, cancelled_at=date.today())
    assert cancelled.can_freeze() is False
    replaced = _sub(
        status=SubscriptionStatus.REPLACED,
        replaced_at=date.today(),
        replaced_by_id=uuid4(),
    )
    assert replaced.can_freeze() is False


# ── can_unfreeze ─────────────────────────────────────────────────────────────


def test_only_frozen_can_be_unfrozen() -> None:
    assert _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today()).can_unfreeze() is True
    assert _sub(status=SubscriptionStatus.ACTIVE).can_unfreeze() is False


# ── can_renew (the expired-rescue case) ──────────────────────────────────────


def test_active_sub_can_renew() -> None:
    """Renew ahead-of-expiry — the normal cash-payment flow."""
    assert _sub(status=SubscriptionStatus.ACTIVE).can_renew() is True


def test_expired_sub_can_renew() -> None:
    """Rescue a lapsed member — same row, new expires_at, tenure preserved."""
    s = _sub(status=SubscriptionStatus.EXPIRED, expired_at=date(2026, 4, 15))
    assert s.can_renew() is True


def test_cancelled_sub_cannot_renew() -> None:
    """Cancel is hard-terminal — the member actively left. Rejoin = new sub."""
    s = _sub(status=SubscriptionStatus.CANCELLED, cancelled_at=date.today())
    assert s.can_renew() is False


def test_frozen_sub_cannot_renew_directly() -> None:
    """Frozen subs must be unfrozen first. Otherwise the freeze-extends-expiry
    math gets weird if we renew in the middle of a freeze."""
    s = _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today())
    assert s.can_renew() is False


def test_replaced_sub_cannot_renew() -> None:
    s = _sub(
        status=SubscriptionStatus.REPLACED,
        replaced_at=date.today(),
        replaced_by_id=uuid4(),
    )
    assert s.can_renew() is False


# ── can_change_plan ──────────────────────────────────────────────────────────


def test_active_and_frozen_can_change_plan() -> None:
    assert _sub(status=SubscriptionStatus.ACTIVE).can_change_plan() is True
    frozen = _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today())
    assert frozen.can_change_plan() is True


def test_expired_cannot_change_plan() -> None:
    """Expired subs must renew first OR start a new sub on the new plan."""
    s = _sub(status=SubscriptionStatus.EXPIRED, expired_at=date.today())
    assert s.can_change_plan() is False


def test_cancelled_and_replaced_cannot_change_plan() -> None:
    cancelled = _sub(status=SubscriptionStatus.CANCELLED, cancelled_at=date.today())
    assert cancelled.can_change_plan() is False
    replaced = _sub(
        status=SubscriptionStatus.REPLACED,
        replaced_at=date.today(),
        replaced_by_id=uuid4(),
    )
    assert replaced.can_change_plan() is False


# ── can_cancel ───────────────────────────────────────────────────────────────


def test_active_frozen_expired_can_cancel() -> None:
    assert _sub(status=SubscriptionStatus.ACTIVE).can_cancel() is True
    frozen = _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today())
    assert frozen.can_cancel() is True
    expired = _sub(status=SubscriptionStatus.EXPIRED, expired_at=date.today())
    assert expired.can_cancel() is True


def test_already_cancelled_cannot_cancel_again() -> None:
    s = _sub(status=SubscriptionStatus.CANCELLED, cancelled_at=date.today())
    assert s.can_cancel() is False


def test_replaced_cannot_cancel() -> None:
    """Replaced is terminal — the new sub is what's live."""
    s = _sub(
        status=SubscriptionStatus.REPLACED,
        replaced_at=date.today(),
        replaced_by_id=uuid4(),
    )
    assert s.can_cancel() is False


# ── should_auto_unfreeze (nightly job) ───────────────────────────────────────


def test_should_auto_unfreeze_when_frozen_until_has_passed() -> None:
    s = _sub(
        status=SubscriptionStatus.FROZEN,
        frozen_at=date(2026, 4, 1),
        frozen_until=date(2026, 4, 10),
    )
    assert s.should_auto_unfreeze(today=date(2026, 4, 11)) is True


def test_should_auto_unfreeze_on_the_exact_day() -> None:
    """Boundary: frozen_until == today should unfreeze (<=, not <)."""
    s = _sub(
        status=SubscriptionStatus.FROZEN,
        frozen_at=date(2026, 4, 1),
        frozen_until=date(2026, 4, 10),
    )
    assert s.should_auto_unfreeze(today=date(2026, 4, 10)) is True


def test_should_not_auto_unfreeze_before_frozen_until() -> None:
    s = _sub(
        status=SubscriptionStatus.FROZEN,
        frozen_at=date(2026, 4, 1),
        frozen_until=date(2026, 4, 10),
    )
    assert s.should_auto_unfreeze(today=date(2026, 4, 9)) is False


def test_open_ended_freeze_is_not_auto_unfrozen() -> None:
    """frozen_until=None means manual-only — the job must not touch it."""
    s = _sub(
        status=SubscriptionStatus.FROZEN,
        frozen_at=date(2026, 4, 1),
        frozen_until=None,
    )
    assert s.should_auto_unfreeze(today=date(2026, 12, 1)) is False


def test_active_sub_is_not_auto_unfrozen() -> None:
    assert _sub(status=SubscriptionStatus.ACTIVE).should_auto_unfreeze(today=date.today()) is False


# ── should_auto_expire (nightly job) ─────────────────────────────────────────


def test_should_auto_expire_when_expires_at_is_in_the_past() -> None:
    s = _sub(
        status=SubscriptionStatus.ACTIVE,
        expires_at=date(2026, 4, 10),
    )
    assert s.should_auto_expire(today=date(2026, 4, 11)) is True


def test_should_not_auto_expire_on_the_exact_day() -> None:
    """Boundary: expires_at == today is still active. Flip happens on the NEXT day
    so the member has the full paid-for day."""
    s = _sub(
        status=SubscriptionStatus.ACTIVE,
        expires_at=date(2026, 4, 10),
    )
    assert s.should_auto_expire(today=date(2026, 4, 10)) is False


def test_card_auto_sub_never_auto_expires() -> None:
    """expires_at=None → card-auto → never expires from a date. Manual cancel only."""
    s = _sub(status=SubscriptionStatus.ACTIVE, expires_at=None)
    assert s.should_auto_expire(today=date(2026, 12, 31)) is False


def test_already_expired_sub_is_not_re_expired() -> None:
    s = _sub(
        status=SubscriptionStatus.EXPIRED,
        expired_at=date(2026, 4, 10),
        expires_at=date(2026, 4, 10),
    )
    assert s.should_auto_expire(today=date(2026, 4, 20)) is False


def test_frozen_sub_does_not_auto_expire() -> None:
    """Frozen subs are paused — paid time doesn't tick, so expiry shouldn't either.
    When they unfreeze, expires_at will have been extended by the frozen duration."""
    s = _sub(
        status=SubscriptionStatus.FROZEN,
        frozen_at=date(2026, 4, 1),
        expires_at=date(2026, 4, 5),
    )
    assert s.should_auto_expire(today=date(2026, 4, 20)) is False


# ── is_live ──────────────────────────────────────────────────────────────────


def test_is_live_matches_partial_unique_predicate() -> None:
    """Mirrors the DB's ``uq_subs_one_live_per_member`` predicate."""
    assert _sub(status=SubscriptionStatus.ACTIVE).is_live() is True
    assert _sub(status=SubscriptionStatus.FROZEN, frozen_at=date.today()).is_live() is True
    assert _sub(status=SubscriptionStatus.EXPIRED, expired_at=date.today()).is_live() is False
    assert _sub(status=SubscriptionStatus.CANCELLED, cancelled_at=date.today()).is_live() is False


# ── days_late (the retention telemetry) ──────────────────────────────────────


def test_days_late_zero_when_not_expired() -> None:
    assert _sub(status=SubscriptionStatus.ACTIVE).days_late(renewed_on=date.today()) == 0


def test_days_late_computes_from_expired_at() -> None:
    s = _sub(
        status=SubscriptionStatus.EXPIRED,
        expired_at=date(2026, 4, 15),
    )
    assert s.days_late(renewed_on=date(2026, 4, 18)) == 3


def test_days_late_clamps_to_zero_for_negative() -> None:
    """Defensive: renewed_on before expired_at shouldn't go negative."""
    s = _sub(
        status=SubscriptionStatus.EXPIRED,
        expired_at=date(2026, 4, 20),
    )
    assert s.days_late(renewed_on=date(2026, 4, 15)) == 0


# ── SubscriptionEvent construction ───────────────────────────────────────────


def test_event_defaults_to_empty_payload_and_nullable_created_by() -> None:
    e = SubscriptionEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        subscription_id=uuid4(),
        event_type=SubscriptionEventType.EXPIRED,
        occurred_at=datetime.now(UTC),
    )
    assert e.event_data == {}
    assert e.created_by is None  # system event


# ── PaymentMethod enum & fields ──────────────────────────────────────────────


def test_payment_method_defaults_to_cash() -> None:
    """Most gyms in IL take cash by default — the Pydantic default should match."""
    s = _sub()
    assert s.payment_method == PaymentMethod.CASH
    assert s.payment_method_detail is None


def test_payment_method_accepts_standing_order_with_null_expires() -> None:
    """Card auto-debit: expires_at=None paired with standing_order is the
    canonical 'runs until cancelled' combo."""
    s = _sub(payment_method=PaymentMethod.STANDING_ORDER, expires_at=None)
    assert s.payment_method == PaymentMethod.STANDING_ORDER
    assert s.expires_at is None


def test_payment_method_other_allows_free_text_detail() -> None:
    s = _sub(
        payment_method=PaymentMethod.OTHER,
        payment_method_detail="bank transfer, reference 12345",
    )
    assert s.payment_method == PaymentMethod.OTHER
    assert s.payment_method_detail == "bank transfer, reference 12345"


def test_payment_method_enum_values() -> None:
    """Guard against typos in the StrEnum — the values flow into the DB CHECK."""
    assert PaymentMethod.CASH.value == "cash"
    assert PaymentMethod.CREDIT_CARD.value == "credit_card"
    assert PaymentMethod.STANDING_ORDER.value == "standing_order"
    assert PaymentMethod.OTHER.value == "other"


def test_event_carries_days_late_on_renewal() -> None:
    """The owner's 'late renewals this month' query reads event_data.days_late."""
    e = SubscriptionEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        subscription_id=uuid4(),
        event_type=SubscriptionEventType.RENEWED,
        event_data={"days_late": 3, "new_expires_at": "2026-05-18"},
        occurred_at=datetime.now(UTC),
        created_by=uuid4(),
    )
    assert e.event_data["days_late"] == 3
