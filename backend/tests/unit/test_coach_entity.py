"""Unit tests for the Coach domain entity's pure logic methods."""

from datetime import UTC, date, datetime
from uuid import uuid4

from app.domain.entities.coach import Coach, CoachStatus


def _make_coach(
    status: CoachStatus = CoachStatus.ACTIVE,
    user_id=None,
) -> Coach:
    now = datetime.now(UTC)
    return Coach(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=user_id,
        first_name="דוד",
        last_name="כהן",
        phone="+972-50-123-4567",
        hired_at=date(2026, 1, 1),
        status=status,
        frozen_at=now if status == CoachStatus.FROZEN else None,
        cancelled_at=now if status == CoachStatus.CANCELLED else None,
        created_at=now,
        updated_at=now,
    )


def test_full_name_joins_first_and_last() -> None:
    assert _make_coach().full_name == "דוד כהן"


def test_is_active_only_for_active_status() -> None:
    assert _make_coach(CoachStatus.ACTIVE).is_active() is True
    assert _make_coach(CoachStatus.FROZEN).is_active() is False
    assert _make_coach(CoachStatus.CANCELLED).is_active() is False


def test_can_freeze_only_when_active() -> None:
    assert _make_coach(CoachStatus.ACTIVE).can_freeze() is True
    assert _make_coach(CoachStatus.FROZEN).can_freeze() is False
    assert _make_coach(CoachStatus.CANCELLED).can_freeze() is False


def test_can_unfreeze_only_when_frozen() -> None:
    assert _make_coach(CoachStatus.FROZEN).can_unfreeze() is True
    assert _make_coach(CoachStatus.ACTIVE).can_unfreeze() is False
    assert _make_coach(CoachStatus.CANCELLED).can_unfreeze() is False


def test_can_cancel_blocks_only_already_cancelled() -> None:
    assert _make_coach(CoachStatus.ACTIVE).can_cancel() is True
    assert _make_coach(CoachStatus.FROZEN).can_cancel() is True
    assert _make_coach(CoachStatus.CANCELLED).can_cancel() is False


def test_can_login_requires_linked_user() -> None:
    assert _make_coach(user_id=None).can_login() is False
    assert _make_coach(user_id=uuid4()).can_login() is True


def test_custom_attrs_defaults_to_empty_dict() -> None:
    assert _make_coach().custom_attrs == {}
