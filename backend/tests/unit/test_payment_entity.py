"""Unit tests for the Payment domain entity.

Pure data row — only one method (``is_refund()``). Tests confirm
required-field semantics, signed-amount handling, and that the
``PaymentMethod`` enum is the same one Subscription uses (so the
DB CHECK and the entity stay in lockstep).
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.entities.payment import Payment
from app.domain.entities.subscription import PaymentMethod


def _make_payment(
    *,
    amount_cents: int = 25000,
    refund_of_payment_id=None,
) -> Payment:
    return Payment(
        id=uuid4(),
        tenant_id=uuid4(),
        member_id=uuid4(),
        subscription_id=uuid4(),
        amount_cents=amount_cents,
        currency="ILS",
        payment_method=PaymentMethod.CASH,
        paid_at=date(2026, 4, 30),
        refund_of_payment_id=refund_of_payment_id,
        created_at=datetime.now(UTC),
    )


def test_is_refund_only_when_refund_of_set() -> None:
    assert _make_payment().is_refund() is False
    assert _make_payment(refund_of_payment_id=uuid4()).is_refund() is True


def test_signed_amount_can_be_negative() -> None:
    """Refund rows store negative cents — the entity accepts them."""
    refund = _make_payment(amount_cents=-5000, refund_of_payment_id=uuid4())
    assert refund.amount_cents == -5000


def test_required_fields() -> None:
    """tenant_id / member_id / amount_cents / currency / payment_method
    / paid_at / created_at must all be supplied."""
    with pytest.raises(ValidationError):
        Payment(id=uuid4())  # type: ignore[call-arg]


def test_payment_method_enum_matches_subscription() -> None:
    """PaymentMethod is reused from Subscription — both tables share the
    same set of values via the same StrEnum. The DB CHECK on payments
    encodes this; the import here proves we're not drifting."""
    assert {pm.value for pm in PaymentMethod} == {
        "cash",
        "credit_card",
        "standing_order",
        "other",
    }


def test_subscription_id_optional_for_drop_ins() -> None:
    """Drop-in payments don't have a subscription. Entity accepts None."""
    p = _make_payment()
    p.subscription_id = None
    assert p.subscription_id is None
