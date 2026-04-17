"""Unit tests for the quota-check pure helpers.

``_find_matching_entitlement`` and ``_compute_window_start`` are the
heart of the attendance feature. Testing them without touching the DB
lets us iterate on edge cases fast — in particular the rolling-week
math that trips everyone up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from app.domain.entities.membership_plan import (
    BillingPeriod,
    PlanEntitlement,
    ResetPeriod,
)
from app.services.attendance_service import (
    _compute_window_start,
    _find_matching_entitlement,
)


def _ent(**overrides) -> PlanEntitlement:
    base = dict(
        id=uuid4(),
        plan_id=uuid4(),
        class_id=None,
        quantity=3,
        reset_period=ResetPeriod.WEEKLY,
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    return PlanEntitlement(**base)


# ── _find_matching_entitlement: exact beats wildcard ─────────────────────────


def test_no_entitlements_returns_none() -> None:
    assert _find_matching_entitlement([], uuid4()) is None


def test_exact_class_match_wins_over_wildcard() -> None:
    yoga_id = uuid4()
    wildcard = _ent(class_id=None, quantity=100)
    yoga_rule = _ent(class_id=yoga_id, quantity=3)
    entitlements = [wildcard, yoga_rule]

    match = _find_matching_entitlement(entitlements, yoga_id)
    assert match is yoga_rule, "exact class rule should beat wildcard"


def test_wildcard_matches_when_no_exact_rule_exists() -> None:
    spinning_id = uuid4()
    wildcard = _ent(class_id=None, quantity=100)
    yoga_rule = _ent(class_id=uuid4(), quantity=3)  # different class

    match = _find_matching_entitlement([wildcard, yoga_rule], spinning_id)
    assert match is wildcard


def test_no_match_when_neither_exact_nor_wildcard() -> None:
    yoga_id = uuid4()
    spinning_id = uuid4()
    yoga_rule = _ent(class_id=yoga_id)
    match = _find_matching_entitlement([yoga_rule], spinning_id)
    assert match is None


def test_exact_match_independent_of_order() -> None:
    """Order of entitlements shouldn't matter — exact always wins."""
    yoga_id = uuid4()
    wildcard = _ent(class_id=None)
    yoga_rule = _ent(class_id=yoga_id)

    # exact before wildcard
    assert _find_matching_entitlement([yoga_rule, wildcard], yoga_id) is yoga_rule
    # wildcard before exact
    assert _find_matching_entitlement([wildcard, yoga_rule], yoga_id) is yoga_rule


# ── _compute_window_start: UNLIMITED ─────────────────────────────────────────


def test_unlimited_returns_unix_epoch_sentinel() -> None:
    """UNLIMITED should never be called in the quota path (caller
    short-circuits), but return a far-past sentinel defensively."""
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.UNLIMITED,
        now=now,
        sub_started_at=date(2026, 4, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(1970, 1, 1, tzinfo=UTC)


# ── _compute_window_start: WEEKLY (Sunday 00:00 UTC) ───────────────────────


def test_weekly_resets_to_sunday_midnight_utc() -> None:
    """2026-04-17 is a Friday. Previous Sunday = 2026-04-12."""
    now = datetime(2026, 4, 17, 14, 30, tzinfo=UTC)  # Friday afternoon
    start = _compute_window_start(
        reset_period=ResetPeriod.WEEKLY,
        now=now,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 12, 0, 0, tzinfo=UTC)


def test_weekly_on_sunday_itself_returns_same_midnight() -> None:
    """Boundary: on Sunday, the window starts at today's 00:00."""
    # 2026-04-12 is a Sunday
    sunday = datetime(2026, 4, 12, 9, 30, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.WEEKLY,
        now=sunday,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 12, 0, 0, tzinfo=UTC)


def test_weekly_on_monday_returns_yesterday_sunday() -> None:
    """2026-04-13 is Monday. Rolling week starts at Sunday 2026-04-12."""
    monday = datetime(2026, 4, 13, 7, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.WEEKLY,
        now=monday,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 12, 0, 0, tzinfo=UTC)


def test_weekly_on_saturday_returns_last_sunday() -> None:
    """Saturday is day 6 of the week (farthest from Sunday)."""
    saturday = datetime(2026, 4, 18, 23, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.WEEKLY,
        now=saturday,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 12, 0, 0, tzinfo=UTC)


# ── _compute_window_start: MONTHLY ─────────────────────────────────────────


def test_monthly_resets_to_first_of_month() -> None:
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.MONTHLY,
        now=now,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)


def test_monthly_on_first_of_month_at_any_hour() -> None:
    """Boundary: on the 1st, the window starts at 00:00 of the 1st."""
    now = datetime(2026, 4, 1, 23, 59, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.MONTHLY,
        now=now,
        sub_started_at=date(2026, 1, 1),
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)


# ── _compute_window_start: BILLING_PERIOD ─────────────────────────────────


def test_billing_period_monthly_computes_current_cycle_start() -> None:
    """Sub started 2026-01-15 with monthly billing. Current cycle starts
    after (elapsed_days // 30) * 30 days from start."""
    sub_started = date(2026, 1, 15)
    # 2026-04-17 is 92 days after 2026-01-15 → 3 full 30-day cycles
    # → current cycle started at 2026-01-15 + 90 days = 2026-04-15
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.BILLING_PERIOD,
        now=now,
        sub_started_at=sub_started,
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 4, 15, 0, 0, tzinfo=UTC)


def test_billing_period_yearly_stays_on_the_first_cycle_most_of_the_time() -> None:
    """Yearly billing: current cycle starts at sub_started_at until 365 days pass."""
    sub_started = date(2026, 1, 15)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)  # 137 days in; well under 365
    start = _compute_window_start(
        reset_period=ResetPeriod.BILLING_PERIOD,
        now=now,
        sub_started_at=sub_started,
        billing_period=BillingPeriod.YEARLY,
    )
    assert start == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


# ── _compute_window_start: NEVER ───────────────────────────────────────────


def test_never_returns_sub_start_timestamp() -> None:
    """'Total across the sub' — window = sub.started_at."""
    sub_started = date(2026, 1, 1)
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    start = _compute_window_start(
        reset_period=ResetPeriod.NEVER,
        now=now,
        sub_started_at=sub_started,
        billing_period=BillingPeriod.MONTHLY,
    )
    assert start == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


# ── Integration-ish sanity: sum of weekly window = 7 days ───────────────


def test_weekly_window_covers_exactly_seven_days() -> None:
    """Defensive: whatever day we're on, window_start → now should be
    at most 7 days. Random sample the whole week."""
    for day_offset in range(14):
        now = datetime(2026, 4, 5, 12, 0, tzinfo=UTC) + timedelta(days=day_offset)
        start = _compute_window_start(
            reset_period=ResetPeriod.WEEKLY,
            now=now,
            sub_started_at=date(2026, 1, 1),
            billing_period=BillingPeriod.MONTHLY,
        )
        diff = now - start
        assert 0 <= diff.days <= 7, f"day {now} → window {start} is {diff}"
