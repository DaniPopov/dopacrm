"""Pydantic domain entity for class sessions.

A session is one concrete occurrence of a class — "boxing on
2026-05-12 at 18:00 UTC, head coach David." Materialized from a
template (or ad-hoc with ``template_id = None``).

State machine: ``scheduled`` or ``cancelled``. "Completed" is derived
(``ends_at < now``), not stored.

``is_customized`` tracks whether the owner has edited this session —
cancelled it, swapped coach, shifted time. Set to True on any
service-layer mutation; used by re-materialization to avoid stomping
manual choices.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    """Lifecycle status of a scheduled session."""

    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class ClassSession(BaseModel):
    """One concrete occurrence of a class."""

    id: UUID
    tenant_id: UUID
    class_id: UUID

    template_id: UUID | None = Field(
        default=None,
        description="Back-pointer. None for ad-hoc sessions.",
    )

    starts_at: datetime
    ends_at: datetime

    head_coach_id: UUID | None = None
    assistant_coach_id: UUID | None = None

    status: SessionStatus = SessionStatus.SCHEDULED
    is_customized: bool = Field(
        default=False,
        description=(
            "True once the owner has manually edited this session "
            "(cancel / swap coach / shift time). Template "
            "re-materialization skips these rows so manual choices "
            "aren't stomped."
        ),
    )

    cancelled_at: datetime | None = None
    cancelled_by: UUID | None = None
    cancellation_reason: str | None = None

    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    # ── Pure state-machine helpers ──────────────────────────────────

    def is_live(self, now: datetime) -> bool:
        """True if this session is currently running (caller gives now for testability).

        Used by the attendance attribution lookup — a ``scheduled``
        session with ``starts_at ≤ now ≤ ends_at`` is the happy case.
        """
        return (
            self.status == SessionStatus.SCHEDULED
            and self.starts_at <= now <= self.ends_at
        )

    def is_completed(self, now: datetime) -> bool:
        """True if a scheduled session has finished (no attendance allowed past its end
        in the regular flow, but still eligible for earnings attribution)."""
        return self.status == SessionStatus.SCHEDULED and self.ends_at < now

    def duration_minutes(self) -> int:
        """Session length in whole minutes."""
        return int((self.ends_at - self.starts_at).total_seconds() / 60)

    def can_cancel(self) -> bool:
        """Only scheduled sessions can be cancelled. Idempotent-on-cancelled."""
        return self.status == SessionStatus.SCHEDULED

    def can_swap_coach(self) -> bool:
        """Swapping a coach on a cancelled session makes no sense."""
        return self.status == SessionStatus.SCHEDULED

    def can_edit_time(self) -> bool:
        """Same — cancelled sessions don't shift."""
        return self.status == SessionStatus.SCHEDULED
