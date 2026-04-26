"""Unit tests for the ClassScheduleTemplate domain entity."""

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest

from app.domain.entities.class_schedule_template import ClassScheduleTemplate


def _make(
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


# ── validators ────────────────────────────────────────────────────────


def test_weekdays_cannot_be_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        _make(weekdays=[])


def test_invalid_weekday_rejected() -> None:
    with pytest.raises(ValueError, match="invalid weekday"):
        _make(weekdays=["mon", "funday"])


def test_duplicate_weekday_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _make(weekdays=["sun", "sun"])


def test_end_time_equal_to_start_rejected() -> None:
    with pytest.raises(ValueError, match="after start_time"):
        _make(start_time=time(18, 0), end_time=time(18, 0))


def test_end_time_before_start_rejected() -> None:
    with pytest.raises(ValueError, match="after start_time"):
        _make(start_time=time(19, 0), end_time=time(18, 0))


def test_ends_on_before_starts_on_rejected() -> None:
    with pytest.raises(ValueError, match="on or after"):
        _make(starts_on=date(2026, 4, 1), ends_on=date(2026, 3, 1))


# ── covers() ──────────────────────────────────────────────────────────


def test_covers_returns_false_when_inactive() -> None:
    t = _make(is_active=False)
    # 2026-04-19 is a Sunday — would otherwise match.
    assert t.covers(date(2026, 4, 19)) is False


def test_covers_before_starts_on_returns_false() -> None:
    t = _make(starts_on=date(2026, 5, 1))
    assert t.covers(date(2026, 4, 19)) is False


def test_covers_after_ends_on_returns_false() -> None:
    t = _make(starts_on=date(2026, 1, 1), ends_on=date(2026, 3, 31))
    assert t.covers(date(2026, 4, 19)) is False


def test_covers_matches_listed_weekday() -> None:
    t = _make(weekdays=["sun", "tue"], starts_on=date(2026, 1, 1))
    assert t.covers(date(2026, 4, 19)) is True  # sunday
    assert t.covers(date(2026, 4, 21)) is True  # tuesday


def test_covers_rejects_unlisted_weekday() -> None:
    t = _make(weekdays=["sun"], starts_on=date(2026, 1, 1))
    assert t.covers(date(2026, 4, 20)) is False  # monday


def test_covers_handles_null_ends_on_as_open_ended() -> None:
    t = _make(starts_on=date(2026, 1, 1), ends_on=None)
    # Far-future Sunday should still match. 2030-04-14 is a Sunday.
    assert t.covers(date(2030, 4, 14)) is True
