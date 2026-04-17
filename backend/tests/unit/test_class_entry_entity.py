"""Unit tests for the ClassEntry domain entity.

Covers the two pure predicates that the service + the UI rely on:
- ``is_effective()`` — mirrors the DB's partial-index predicate.
- ``can_undo(now)`` — 24h window math + already-undone guard.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.entities.class_entry import (
    UNDO_WINDOW,
    ClassEntry,
    OverrideKind,
)


def _entry(**overrides) -> ClassEntry:
    base = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        member_id=uuid4(),
        subscription_id=uuid4(),
        class_id=uuid4(),
        entered_at=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        entered_by=uuid4(),
        undone_at=None,
        undone_by=None,
        undone_reason=None,
        override=False,
        override_kind=None,
        override_reason=None,
    )
    base.update(overrides)
    return ClassEntry(**base)


# ── is_effective ─────────────────────────────────────────────────────────────


def test_is_effective_true_when_not_undone() -> None:
    assert _entry().is_effective() is True


def test_is_effective_false_when_undone() -> None:
    e = _entry(undone_at=datetime(2026, 4, 17, 18, 0, tzinfo=UTC), undone_by=uuid4())
    assert e.is_effective() is False


# ── can_undo (24h window + already-undone guard) ────────────────────────────


def test_can_undo_fresh_entry() -> None:
    e = _entry(entered_at=datetime(2026, 4, 17, 12, 0, tzinfo=UTC))
    now = datetime(2026, 4, 17, 13, 0, tzinfo=UTC)
    assert e.can_undo(now=now) is True


def test_can_undo_exactly_on_boundary() -> None:
    """Boundary: exactly 24h → still undoable (<=, not <)."""
    entered = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    e = _entry(entered_at=entered)
    now = entered + UNDO_WINDOW
    assert e.can_undo(now=now) is True


def test_can_undo_just_past_boundary() -> None:
    entered = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    e = _entry(entered_at=entered)
    now = entered + UNDO_WINDOW + timedelta(seconds=1)
    assert e.can_undo(now=now) is False


def test_already_undone_cannot_be_undone_again() -> None:
    """Double-undo guard — even within the window."""
    entered = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    e = _entry(
        entered_at=entered,
        undone_at=datetime(2026, 4, 17, 13, 0, tzinfo=UTC),
        undone_by=uuid4(),
    )
    now = datetime(2026, 4, 17, 14, 0, tzinfo=UTC)  # still within 24h
    assert e.can_undo(now=now) is False


def test_undo_window_is_24_hours_exactly() -> None:
    """Guard the constant — other layers (UI, cron) depend on this value."""
    assert timedelta(hours=24) == UNDO_WINDOW


# ── age ─────────────────────────────────────────────────────────────────────


def test_age_returns_elapsed_time() -> None:
    entered = datetime(2026, 4, 17, 10, 0, tzinfo=UTC)
    e = _entry(entered_at=entered)
    now = datetime(2026, 4, 17, 12, 30, tzinfo=UTC)
    assert e.age(now=now) == timedelta(hours=2, minutes=30)


# ── Override telemetry (pure shape, no logic) ───────────────────────────────


def test_default_is_not_an_override() -> None:
    e = _entry()
    assert e.override is False
    assert e.override_kind is None
    assert e.override_reason is None


def test_override_can_be_quota_exceeded_with_reason() -> None:
    e = _entry(
        override=True,
        override_kind=OverrideKind.QUOTA_EXCEEDED,
        override_reason="birthday class — on the house",
    )
    assert e.override is True
    assert e.override_kind == OverrideKind.QUOTA_EXCEEDED
    assert e.override_reason == "birthday class — on the house"


def test_override_can_be_not_covered() -> None:
    e = _entry(
        override=True,
        override_kind=OverrideKind.NOT_COVERED,
        override_reason=None,
    )
    assert e.override_kind == OverrideKind.NOT_COVERED


def test_override_kind_enum_values() -> None:
    """Guard against typos — the values flow into the DB CHECK constraint."""
    assert OverrideKind.QUOTA_EXCEEDED.value == "quota_exceeded"
    assert OverrideKind.NOT_COVERED.value == "not_covered"
