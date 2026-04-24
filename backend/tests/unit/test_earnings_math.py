"""Unit tests for the pure payroll-math helpers in CoachService.

These run without a DB — they exercise the pro-ration formula, month
boundary handling, leap years, and the coach-lifetime clipping rule.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from app.domain.entities.coach import Coach, CoachStatus
from app.services.coach_service import (
    _coach_effective_window,
    _first_of_next_month,
    fixed_prorated,
)


def _coach(
    *,
    hired_at: date = date(2026, 1, 1),
    status: CoachStatus = CoachStatus.ACTIVE,
    frozen_at: datetime | None = None,
    cancelled_at: datetime | None = None,
) -> Coach:
    now = datetime.now(UTC)
    return Coach(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=None,
        first_name="A",
        last_name="B",
        hired_at=hired_at,
        status=status,
        frozen_at=frozen_at,
        cancelled_at=cancelled_at,
        created_at=now,
        updated_at=now,
    )


# ── fixed_prorated ────────────────────────────────────────────────────


def test_full_month_returns_monthly_amount() -> None:
    assert fixed_prorated(300000, date(2026, 5, 1), date(2026, 5, 31)) == 300000


def test_half_month_prorates_by_day_count() -> None:
    # May has 31 days; 1–15 = 15 days.
    expected = round(300000 * 15 / 31)
    assert fixed_prorated(300000, date(2026, 5, 1), date(2026, 5, 15)) == expected


def test_cross_month_sums_per_month_slice() -> None:
    # Apr 20 → Apr 30 = 11 days / 30
    # May 1  → May 10 = 10 days / 31
    from decimal import ROUND_HALF_EVEN, Decimal

    expected = int(
        (
            Decimal(300000) * Decimal(11) / Decimal(30)
            + Decimal(300000) * Decimal(10) / Decimal(31)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    )
    assert fixed_prorated(300000, date(2026, 4, 20), date(2026, 5, 10)) == expected


def test_leap_year_february_has_29_days() -> None:
    # 2024 is a leap year.
    assert fixed_prorated(290000, date(2024, 2, 1), date(2024, 2, 29)) == 290000
    # Non-leap 2026
    assert fixed_prorated(280000, date(2026, 2, 1), date(2026, 2, 28)) == 280000


def test_single_day() -> None:
    # 1 / 31 * 310000 = 10000
    assert fixed_prorated(310000, date(2026, 5, 1), date(2026, 5, 1)) == 10000


def test_inverted_range_returns_zero() -> None:
    assert fixed_prorated(300000, date(2026, 5, 10), date(2026, 5, 1)) == 0


def test_zero_monthly_is_zero() -> None:
    assert fixed_prorated(0, date(2026, 1, 1), date(2026, 12, 31)) == 0


def test_year_wrap() -> None:
    # Dec 1, 2026 → Jan 31, 2027 spans two different years.
    # Dec 2026 has 31 days, Jan 2027 has 31 days — both full → 2 × monthly.
    assert fixed_prorated(200000, date(2026, 12, 1), date(2027, 1, 31)) == 400000


# ── _first_of_next_month ──────────────────────────────────────────────


def test_first_of_next_month_mid_year() -> None:
    assert _first_of_next_month(date(2026, 3, 15)) == date(2026, 4, 1)


def test_first_of_next_month_december_rolls_year() -> None:
    assert _first_of_next_month(date(2026, 12, 20)) == date(2027, 1, 1)


# ── _coach_effective_window ───────────────────────────────────────────


def test_active_coach_window_is_unchanged() -> None:
    c = _coach(hired_at=date(2026, 1, 1))
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (date(2026, 5, 1), date(2026, 5, 31))


def test_hired_at_clamps_start() -> None:
    c = _coach(hired_at=date(2026, 5, 10))
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (date(2026, 5, 10), date(2026, 5, 31))


def test_cancelled_clamps_end() -> None:
    c = _coach(
        hired_at=date(2026, 1, 1),
        status=CoachStatus.CANCELLED,
        cancelled_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (date(2026, 5, 1), date(2026, 5, 15))


def test_frozen_clamps_end_to_day_before_freeze() -> None:
    c = _coach(
        hired_at=date(2026, 1, 1),
        status=CoachStatus.FROZEN,
        frozen_at=datetime(2026, 5, 16, tzinfo=UTC),
    )
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (date(2026, 5, 1), date(2026, 5, 15))


def test_fully_post_termination_returns_none_none() -> None:
    c = _coach(
        hired_at=date(2026, 1, 1),
        status=CoachStatus.CANCELLED,
        cancelled_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (None, None)


def test_hired_after_window_returns_none_none() -> None:
    c = _coach(hired_at=date(2026, 8, 1))
    eff = _coach_effective_window(c, date(2026, 5, 1), date(2026, 5, 31))
    assert eff == (None, None)
