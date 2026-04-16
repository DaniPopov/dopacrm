"""Pydantic domain entity for a gym class type.

Named ``gym_class`` rather than ``class`` to avoid shadowing Python's
``class`` keyword. The domain class is ``GymClass`` — import as:

    from app.domain.entities.gym_class import GymClass

A gym class is a TYPE of session offered by the gym (Spinning, Yoga,
CrossFit, etc.) — NOT a scheduled session in time. Scheduled sessions,
attendance, and class passes are separate concepts in later features.

Ownership:
- Each class belongs to exactly one tenant (``tenant_id`` NOT NULL).
- Name is unique within a tenant but can repeat across tenants.
- Deactivation is a soft state — passes and attendance that already
  reference a deactivated class keep working; new subscriptions /
  passes can't be created against it.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GymClass(BaseModel):
    """A class type in the gym's catalog ("Spinning", "Yoga", …)."""

    id: UUID
    tenant_id: UUID = Field(description="Gym this class belongs to. All queries scope by this.")

    name: str = Field(description="Display name. Unique within tenant.")
    description: str | None = None
    color: str | None = Field(
        default=None,
        description=(
            "Free-text color hint for the UI (hex recommended, e.g. '#3B82F6'). Not validated."
        ),
    )

    is_active: bool = True

    created_at: datetime
    updated_at: datetime

    def can_be_referenced_by_new_subscription(self) -> bool:
        """New plan_entitlements / class_passes can only point at active classes."""
        return self.is_active
