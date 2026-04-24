"""Unit tests for the ClassCoach domain entity + weekday helpers."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.domain.entities.class_coach import (
    WEEKDAYS,
    ClassCoach,
    PayModel,
    weekday_code,
)


def _make(
    *,
    weekdays: list[str] | None = None,
    starts_on: date = date(2026, 1, 1),
    ends_on: date | None = None,
    pay_model: PayModel = PayModel.PER_ATTENDANCE,
    pay_amount_cents: int = 5000,
    is_primary: bool = False,
    role: str = "ראשי",
) -> ClassCoach:
    now = datetime.now(UTC)
    return ClassCoach(
        id=uuid4(),
        tenant_id=uuid4(),
        class_id=uuid4(),
        coach_id=uuid4(),
        role=role,
        is_primary=is_primary,
        pay_model=pay_model,
        pay_amount_cents=pay_amount_cents,
        weekdays=weekdays if weekdays is not None else [],
        starts_on=starts_on,
        ends_on=ends_on,
        created_at=now,
        updated_at=now,
    )


# ── WEEKDAYS + weekday_code helper ─────────────────────────────────────

def test_weekdays_tuple_shape() -> None:
    assert WEEKDAYS == ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def test_weekday_code_sunday_is_sun() -> None:
    # 2026-04-19 is a Sunday in Asia/Jerusalem / UTC.
    assert weekday_code(date(2026, 4, 19)) == "sun"


def test_weekday_code_saturday_is_sat() -> None:
    # 2026-04-18 is a Saturday.
    assert weekday_code(date(2026, 4, 18)) == "sat"


def test_weekday_code_all_seven_distinct() -> None:
    codes = {weekday_code(date(2026, 4, 19 + i)) for i in range(7)}
    assert codes == set(WEEKDAYS)


# ── ClassCoach.covers() ────────────────────────────────────────────────

def test_covers_before_start_returns_false() -> None:
    link = _make(starts_on=date(2026, 5, 1))
    assert link.covers(date(2026, 4, 30)) is False


def test_covers_after_end_returns_false() -> None:
    link = _make(starts_on=date(2026, 4, 1), ends_on=date(2026, 4, 30))
    assert link.covers(date(2026, 5, 1)) is False


def test_covers_empty_weekdays_means_all_days() -> None:
    link = _make(weekdays=[], starts_on=date(2026, 1, 1))
    # Any in-range date should match.
    for i in range(7):
        assert link.covers(date(2026, 4, 19 + i)) is True


def test_covers_restricts_to_listed_weekdays() -> None:
    link = _make(weekdays=["sun", "tue"], starts_on=date(2026, 1, 1))
    assert link.covers(date(2026, 4, 19)) is True   # sunday
    assert link.covers(date(2026, 4, 21)) is True   # tuesday
    assert link.covers(date(2026, 4, 20)) is False  # monday
    assert link.covers(date(2026, 4, 22)) is False  # wednesday


# ── validators ─────────────────────────────────────────────────────────

def test_invalid_weekday_rejected() -> None:
    with pytest.raises(ValueError, match="invalid weekday"):
        _make(weekdays=["mon", "funday"])


def test_duplicate_weekday_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _make(weekdays=["sun", "sun"])


def test_ends_on_before_starts_on_rejected() -> None:
    with pytest.raises(ValueError, match="starts_on"):
        _make(starts_on=date(2026, 4, 20), ends_on=date(2026, 4, 10))


def test_negative_pay_amount_rejected() -> None:
    with pytest.raises(ValueError):
        _make(pay_amount_cents=-1)
