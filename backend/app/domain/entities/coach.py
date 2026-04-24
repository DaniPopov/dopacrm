"""Pydantic domain entity for coaches (trainers).

A coach is a gym's trainer — the person who teaches classes. Unlike
members, a coach **can** log in: ``coaches.user_id`` is an optional 1:1
link to a ``users`` row with ``role='coach'``. A coach without a linked
user is a payroll-only record, which some gyms want (the trainer
doesn't need CRM access).

The entity carries the lifecycle status only. Pay rules + per-class
assignments live on ``ClassCoach`` (see ``class_coach.py``) — they're
per-link, not per-coach.

Lifecycle mirrors Members:

    active ──(freeze)──> frozen ──(unfreeze)──> active
        │                   │
        └──(cancel)─────────┴──> cancelled    (terminal)

Frozen = temporarily off duty (injury, leave). Earnings accrual stops
at ``frozen_at``. Cancelled = the coach has left the gym. Past
``class_entries.coach_id`` are unchanged — payroll history is immutable.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CoachStatus(StrEnum):
    """Lifecycle status of a coach."""

    ACTIVE = "active"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


class Coach(BaseModel):
    """A gym coach / trainer."""

    id: UUID
    tenant_id: UUID = Field(description="Gym this coach works at.")
    user_id: UUID | None = Field(
        default=None,
        description=(
            "Optional FK to the users table. Set when the coach has a login. "
            "Unique across coaches (a user can be linked to at most one coach)."
        ),
    )

    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None

    hired_at: date
    status: CoachStatus = CoachStatus.ACTIVE
    frozen_at: datetime | None = None
    cancelled_at: datetime | None = None

    custom_attrs: dict[str, Any] = Field(
        default_factory=dict,
        description="Owner-configurable extras (certifications, prefs).",
    )

    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def is_active(self) -> bool:
        return self.status == CoachStatus.ACTIVE

    def can_freeze(self) -> bool:
        """Only active coaches can be frozen."""
        return self.status == CoachStatus.ACTIVE

    def can_unfreeze(self) -> bool:
        """Only frozen coaches can be unfrozen."""
        return self.status == CoachStatus.FROZEN

    def can_cancel(self) -> bool:
        """Cancel is terminal — blocked once already cancelled."""
        return self.status != CoachStatus.CANCELLED

    def can_login(self) -> bool:
        """True iff a user row is linked. Drives the coach-portal gate."""
        return self.user_id is not None
