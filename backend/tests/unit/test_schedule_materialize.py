"""Unit tests for the pure materialization helpers."""

from datetime import UTC, date, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.domain.entities.class_schedule_template import ClassScheduleTemplate
from app.services.schedule_materialize import (
    DEFAULT_TENANT_TZ,
    materialize_dates,
    session_timestamps,
)


def _tmpl(
    *,
    weekdays: list[str] | None = None,
    start_time: time = time(18, 0),
    end_time: time = time(19, 0),
    starts_on: date = date(2026, 1, 1),
    ends_on: date | None = None,
    is_active: bool = True,
) -> ClassScheduleTemplate:
    now = datetime.now(UTC)
    return ClassScheduleTemplate(
        id=uuid4(),
        tenant_id=uuid4(),
        class_id=uuid4(),
        weekdays=weekdays if weekdays is not None else ["sun", "tue"],
        start_time=start_time,
        end_time=end_time,
        head_coach_id=uuid4(),
        assistant_coach_id=None,
        starts_on=starts_on,
        ends_on=ends_on,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


# ── materialize_dates ─────────────────────────────────────────────────


def test_materialize_one_week_two_weekdays() -> None:
    t = _tmpl(weekdays=["sun", "tue"], starts_on=date(2026, 1, 1))
    # 2026-04-19 Sun, 2026-04-21 Tue in this range → 2 dates.
    dates = materialize_dates(t, date(2026, 4, 19), date(2026, 4, 25))
    assert dates == [date(2026, 4, 19), date(2026, 4, 21)]


def test_materialize_clips_to_starts_on() -> None:
    t = _tmpl(weekdays=["sun"], starts_on=date(2026, 5, 1))
    # Request earlier — the 2026-04-19 Sunday is BEFORE starts_on.
    dates = materialize_dates(t, date(2026, 4, 15), date(2026, 5, 10))
    # Only Sundays ≥ 2026-05-01: 2026-05-03 and 2026-05-10.
    assert dates == [date(2026, 5, 3), date(2026, 5, 10)]


def test_materialize_clips_to_ends_on() -> None:
    t = _tmpl(weekdays=["sun"], starts_on=date(2026, 1, 1), ends_on=date(2026, 5, 3))
    dates = materialize_dates(t, date(2026, 4, 26), date(2026, 5, 17))
    # Sundays ≤ ends_on: 2026-04-26 and 2026-05-03. 2026-05-10, 2026-05-17 dropped.
    assert dates == [date(2026, 4, 26), date(2026, 5, 3)]


def test_materialize_returns_empty_when_inactive() -> None:
    t = _tmpl(is_active=False)
    assert materialize_dates(t, date(2026, 4, 19), date(2026, 4, 25)) == []


def test_materialize_returns_empty_when_inverted_range() -> None:
    t = _tmpl()
    assert materialize_dates(t, date(2026, 4, 25), date(2026, 4, 19)) == []


def test_materialize_all_seven_days() -> None:
    t = _tmpl(
        weekdays=["sun", "mon", "tue", "wed", "thu", "fri", "sat"],
        starts_on=date(2026, 1, 1),
    )
    dates = materialize_dates(t, date(2026, 4, 19), date(2026, 4, 25))
    # 7 consecutive days starting Sunday = Sun..Sat.
    assert len(dates) == 7
    assert dates[0] == date(2026, 4, 19)
    assert dates[-1] == date(2026, 4, 25)


def test_materialize_leap_day_handled() -> None:
    # 2024 is a leap year. Feb 29 2024 is a Thursday.
    t = _tmpl(weekdays=["thu"], starts_on=date(2024, 1, 1))
    dates = materialize_dates(t, date(2024, 2, 29), date(2024, 2, 29))
    assert dates == [date(2024, 2, 29)]


def test_materialize_single_day_window_match() -> None:
    """from_ == to and the template covers that day → single date."""
    t = _tmpl(weekdays=["sun"], starts_on=date(2026, 1, 1))
    dates = materialize_dates(t, date(2026, 4, 19), date(2026, 4, 19))
    assert dates == [date(2026, 4, 19)]


def test_materialize_single_day_window_no_match() -> None:
    """from_ == to and the template does NOT cover that day → empty."""
    t = _tmpl(weekdays=["sun"], starts_on=date(2026, 1, 1))
    dates = materialize_dates(t, date(2026, 4, 20), date(2026, 4, 20))
    assert dates == []


def test_materialize_stops_at_template_ends_on() -> None:
    """A template that ends mid-window should not yield dates past its
    ends_on, even if the requested window extends further."""
    t = _tmpl(
        weekdays=["sun"],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 4, 19),  # last Sunday in the template
    )
    # Request a much wider window.
    dates = materialize_dates(t, date(2026, 1, 1), date(2026, 12, 31))
    assert date(2026, 4, 19) in dates
    assert all(d <= date(2026, 4, 19) for d in dates)


def test_materialize_inactive_template_yields_nothing_even_in_active_range() -> None:
    """Defensive — if the owner deactivates a template, even querying
    inside its starts_on/ends_on should yield no dates."""
    t = _tmpl(
        weekdays=["sun"],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        is_active=False,
    )
    assert materialize_dates(t, date(2026, 4, 19), date(2026, 4, 19)) == []


# ── session_timestamps ────────────────────────────────────────────────


def test_session_timestamps_utc_conversion() -> None:
    t = _tmpl(start_time=time(18, 0), end_time=time(19, 0))
    starts, ends = session_timestamps(t, date(2026, 4, 19), tenant_tz=ZoneInfo("Asia/Jerusalem"))
    # Israel is UTC+3 in April (DST active from March-October).
    # 18:00 Jerusalem = 15:00 UTC.
    assert starts == datetime(2026, 4, 19, 15, 0, tzinfo=UTC)
    assert ends == datetime(2026, 4, 19, 16, 0, tzinfo=UTC)


def test_session_timestamps_winter_no_dst() -> None:
    # January — Israel on IST (UTC+2).
    t = _tmpl(start_time=time(18, 0), end_time=time(19, 0))
    starts, ends = session_timestamps(t, date(2026, 1, 15), tenant_tz=ZoneInfo("Asia/Jerusalem"))
    # 18:00 Jerusalem = 16:00 UTC in winter.
    assert starts == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)
    assert ends == datetime(2026, 1, 15, 17, 0, tzinfo=UTC)


def test_session_timestamps_default_tz_is_jerusalem() -> None:
    t = _tmpl(start_time=time(6, 0), end_time=time(7, 0))
    starts, _ = session_timestamps(t, date(2026, 4, 19))
    # Same as explicit Asia/Jerusalem — 06:00 IDT = 03:00 UTC in April.
    assert starts == datetime(2026, 4, 19, 3, 0, tzinfo=UTC)


def test_default_tenant_tz_is_jerusalem() -> None:
    assert ZoneInfo("Asia/Jerusalem") == DEFAULT_TENANT_TZ
