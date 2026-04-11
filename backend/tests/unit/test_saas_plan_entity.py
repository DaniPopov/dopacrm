"""Unit tests for the SaasPlan domain entity."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.saas_plan import BillingPeriod, SaasPlan


def _make_plan(**overrides) -> SaasPlan:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "code": "default",
        "name": "DopaCRM Standard",
        "price_cents": 50000,
        "max_members": 1000,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return SaasPlan(**defaults)


def test_default_plan_is_ils_monthly() -> None:
    plan = _make_plan()
    assert plan.currency == "ILS"
    assert plan.billing_period == BillingPeriod.MONTHLY
    assert plan.features == {}
    assert plan.is_public is True
    assert plan.max_staff_users is None  # unlimited


def test_plan_with_staff_cap() -> None:
    plan = _make_plan(max_staff_users=10)
    assert plan.max_staff_users == 10


def test_price_cents_must_be_nonneg() -> None:
    import pytest

    with pytest.raises(ValueError):
        _make_plan(price_cents=-100)


def test_max_members_must_be_nonneg() -> None:
    import pytest

    with pytest.raises(ValueError):
        _make_plan(max_members=-1)
