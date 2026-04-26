"""Pydantic domain entity for a class entry (attendance record).

A ClassEntry is one check-in: "Dana entered yoga at 17:05 today, under
her active subscription, recorded by staff X". It's the highest-volume
write in the CRM (every active member hits it 3-5 times a week), and
the feature that finally validates whether the Plans + Subscriptions
entitlement model actually works in practice.

Two states: recorded vs undone. Soft-delete via ``undone_at`` — the row
never leaves the DB. Quota-counting queries filter by
``WHERE undone_at IS NULL``.

Overrides: staff can bypass a quota limit or check in for a class not
covered by the member's plan. Each override is tagged (``override=true``,
``override_kind``) so dashboards can surface patterns ("staff X
overrode 40× last month" = training or abuse signal).

See ``docs/features/attendance.md`` for the full design + quota math.
"""

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class OverrideKind(StrEnum):
    """Why this entry was an override (null for normal entries)."""

    QUOTA_EXCEEDED = "quota_exceeded"  # entitlement exists but quota was full
    NOT_COVERED = "not_covered"  # no entitlement for this class at all


#: Undo is allowed within 24 hours of the original ``entered_at``.
#: Keep in sync with the spec + the UI, which hides the undo button
#: after the window.
UNDO_WINDOW = timedelta(hours=24)


class ClassEntry(BaseModel):
    """A single check-in."""

    id: UUID
    tenant_id: UUID = Field(description="Tenant scope — every query filters by this.")
    member_id: UUID
    subscription_id: UUID = Field(
        description=(
            "Every entry ties to exactly one live subscription. No subscriptionless entries."
        )
    )
    class_id: UUID

    entered_at: datetime
    entered_by: UUID | None = Field(
        default=None,
        description="Staff who recorded the entry. None only if the user was later deleted.",
    )

    # Soft-delete / undo
    undone_at: datetime | None = None
    undone_by: UUID | None = None
    undone_reason: str | None = None

    # Override telemetry
    override: bool = Field(
        default=False,
        description=(
            "True iff staff bypassed a quota or checked in for a non-covered class. "
            "Paired with override_kind + optional override_reason."
        ),
    )
    override_kind: OverrideKind | None = None
    override_reason: str | None = None

    # Coach attribution — set at INSERT by the attendance service via the
    # class_coaches weekday lookup. Immutable history; corrections go
    # through POST /attendance/{id}/reassign-coach. Nullable for entries
    # recorded before Coaches shipped + cases where no coach matched.
    coach_id: UUID | None = None

    # Session attribution — set at INSERT when the attendance service
    # finds a scheduled session overlapping entered_at (Schedule feature
    # required). NULL for drop-ins and tenants with Schedule off.
    # Immutable.
    session_id: UUID | None = None

    # ── Pure state-machine helpers ─────────────────────────────────────

    def is_effective(self) -> bool:
        """True if this entry counts toward usage (i.e., not undone).

        Every quota-count query + every report filters out non-effective
        rows. Mirrors the partial index on ``class_entries``.
        """
        return self.undone_at is None

    def can_undo(self, now: datetime) -> bool:
        """True if the entry is still within the 24-hour undo window
        and hasn't been undone already. Caller supplies ``now`` for
        testability.

        Does NOT enforce who-can-undo (that's a service-layer concern —
        the creator or the owner).
        """
        if self.undone_at is not None:
            return False
        return (now - self.entered_at) <= UNDO_WINDOW

    def age(self, now: datetime) -> timedelta:
        """How long ago this entry was recorded."""
        return now - self.entered_at
