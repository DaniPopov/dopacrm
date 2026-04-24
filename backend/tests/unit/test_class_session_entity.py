"""Unit tests for the ClassSession domain entity."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.entities.class_session import ClassSession, SessionStatus


def _make(
    *,
    status: SessionStatus = SessionStatus.SCHEDULED,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_customized: bool = False,
) -> ClassSession:
    now = datetime.now(UTC)
    starts_at = starts_at or (now + timedelta(hours=1))
    ends_at = ends_at or (starts_at + timedelta(hours=1))
    return ClassSession(
        id=uuid4(),
        tenant_id=uuid4(),
        class_id=uuid4(),
        template_id=None,
        starts_at=starts_at,
        ends_at=ends_at,
        head_coach_id=uuid4(),
        status=status,
        is_customized=is_customized,
        cancelled_at=now if status == SessionStatus.CANCELLED else None,
        created_at=now,
        updated_at=now,
    )


# ── is_live ───────────────────────────────────────────────────────────


def test_is_live_true_when_now_in_range() -> None:
    now = datetime(2026, 4, 19, 18, 30, tzinfo=UTC)
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_live(now) is True


def test_is_live_false_before_start() -> None:
    now = datetime(2026, 4, 19, 17, 30, tzinfo=UTC)
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_live(now) is False


def test_is_live_false_after_end() -> None:
    now = datetime(2026, 4, 19, 19, 30, tzinfo=UTC)
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_live(now) is False


def test_cancelled_never_live() -> None:
    now = datetime(2026, 4, 19, 18, 30, tzinfo=UTC)
    s = _make(
        status=SessionStatus.CANCELLED,
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_live(now) is False


# ── is_completed ──────────────────────────────────────────────────────


def test_is_completed_after_end() -> None:
    now = datetime(2026, 4, 19, 20, 0, tzinfo=UTC)
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_completed(now) is True


def test_is_completed_false_before_end() -> None:
    now = datetime(2026, 4, 19, 18, 30, tzinfo=UTC)
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_completed(now) is False


def test_cancelled_not_completed() -> None:
    now = datetime(2026, 4, 19, 20, 0, tzinfo=UTC)
    s = _make(
        status=SessionStatus.CANCELLED,
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 0, tzinfo=UTC),
    )
    assert s.is_completed(now) is False


# ── duration ──────────────────────────────────────────────────────────


def test_duration_minutes() -> None:
    s = _make(
        starts_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 19, 19, 30, tzinfo=UTC),
    )
    assert s.duration_minutes() == 90


# ── state transitions ────────────────────────────────────────────────


def test_can_cancel_only_when_scheduled() -> None:
    assert _make(status=SessionStatus.SCHEDULED).can_cancel() is True
    assert _make(status=SessionStatus.CANCELLED).can_cancel() is False


def test_can_swap_only_when_scheduled() -> None:
    assert _make(status=SessionStatus.SCHEDULED).can_swap_coach() is True
    assert _make(status=SessionStatus.CANCELLED).can_swap_coach() is False


def test_can_edit_time_only_when_scheduled() -> None:
    assert _make(status=SessionStatus.SCHEDULED).can_edit_time() is True
    assert _make(status=SessionStatus.CANCELLED).can_edit_time() is False


# ── is_customized default ─────────────────────────────────────────────


def test_is_customized_default_false() -> None:
    assert _make().is_customized is False
