"""Unit tests for the GymClass domain entity."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.gym_class import GymClass


def _make_class(*, is_active: bool = True) -> GymClass:
    now = datetime.now(UTC)
    return GymClass(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Spinning",
        description="High-intensity indoor cycling",
        color="#3B82F6",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def test_active_class_can_be_referenced_by_new_subscription() -> None:
    assert _make_class(is_active=True).can_be_referenced_by_new_subscription() is True


def test_deactivated_class_cannot_be_referenced_by_new_subscription() -> None:
    assert _make_class(is_active=False).can_be_referenced_by_new_subscription() is False


def test_description_and_color_are_optional() -> None:
    now = datetime.now(UTC)
    cls = GymClass(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Yoga",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert cls.description is None
    assert cls.color is None


def test_is_active_defaults_to_true() -> None:
    now = datetime.now(UTC)
    cls = GymClass(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Yoga",
        created_at=now,
        updated_at=now,
    )
    assert cls.is_active is True
