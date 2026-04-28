"""Pydantic domain entity for leads (sales pipeline records).

A lead is a prospective member moving through ``new → contacted →
trial → converted`` (or ``lost``). Every gym walk-in / website inquiry
/ referral lives here until it converts into a real Member or is
marked lost.

Trial is a status, not a side-effect. Putting a lead in ``trial`` does
NOT create a Subscription or grant class access — that responsibility
belongs to the convert flow, where the lead becomes a Member with a
real first Subscription in one transaction.

The state machine:

    new ─────► contacted ─────► trial ─────► CONVERTED  (terminal)
      │            │              │
      └────────────┴──────────────┴──► lost ──(reopen)──► contacted

- Forward skips are allowed (a walk-in can convert on the spot, jumping
  ``new → converted``). The matrix below encodes every legal move.
- ``converted`` is terminal AND only reachable through the convert
  endpoint, which atomically writes Member + Subscription. Drag-to-
  converted from the simple status PATCH is rejected.
- ``lost`` is reversible — reopen sets status back to ``contacted`` and
  clears ``lost_reason`` (the historical reason stays in the activity
  row).

See ``docs/features/leads.md`` for the full design + UI sketch.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LeadStatus(StrEnum):
    """Pipeline status of a lead."""

    NEW = "new"
    CONTACTED = "contacted"
    TRIAL = "trial"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(StrEnum):
    """How the lead came in. Drives the 'where do members come from?' report."""

    WALK_IN = "walk_in"
    WEBSITE = "website"
    REFERRAL = "referral"
    SOCIAL_MEDIA = "social_media"
    AD = "ad"
    OTHER = "other"


#: State transition matrix. Keys are the *current* status; values are the
#: set of allowed *next* statuses through the simple ``set_status`` path.
#: ``CONVERTED`` is excluded as a target everywhere — converting must go
#: through ``LeadService.convert`` (which writes Member + Subscription
#: atomically). ``CONVERTED`` is terminal as a source.
_ALLOWED_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset({LeadStatus.CONTACTED, LeadStatus.TRIAL, LeadStatus.LOST}),
    LeadStatus.CONTACTED: frozenset({LeadStatus.TRIAL, LeadStatus.LOST}),
    LeadStatus.TRIAL: frozenset({LeadStatus.CONTACTED, LeadStatus.LOST}),
    LeadStatus.CONVERTED: frozenset(),  # terminal
    LeadStatus.LOST: frozenset({LeadStatus.CONTACTED}),  # reopen path
}


class Lead(BaseModel):
    """A sales pipeline lead."""

    id: UUID
    tenant_id: UUID = Field(description="Gym this lead belongs to.")

    first_name: str
    last_name: str
    email: str | None = None
    phone: str
    source: LeadSource = LeadSource.OTHER
    status: LeadStatus = LeadStatus.NEW
    assigned_to: UUID | None = Field(
        default=None,
        description=(
            "Optional FK to users. Routing/reporting only — sales sees all "
            "leads in the tenant today. Per-rep partitioning is a Phase 4 "
            "config toggle."
        ),
    )
    notes: str | None = None
    lost_reason: str | None = Field(
        default=None,
        description=(
            "Set when status moves to lost; cleared on reopen. The "
            "historical reason is preserved in the matching status_change "
            "activity row."
        ),
    )
    converted_member_id: UUID | None = Field(
        default=None,
        description="FK to the Member created by the convert endpoint.",
    )

    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for per-tenant fields. No UI in v1.",
    )

    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def is_open(self) -> bool:
        """True iff the lead is still actionable (not converted or lost)."""
        return self.status not in {LeadStatus.CONVERTED, LeadStatus.LOST}

    def can_transition_to(self, new_status: LeadStatus) -> bool:
        """Is ``status → new_status`` a legal move via the simple
        ``set_status`` path?

        Returns False for ``new_status == CONVERTED`` always — converting
        requires the dedicated endpoint that takes a plan.
        Returns False from ``CONVERTED`` (terminal source).
        """
        if new_status == LeadStatus.CONVERTED:
            return False
        if new_status == self.status:
            # No-op — not "illegal" per se, but service rejects to avoid
            # ghost status_change rows.
            return False
        return new_status in _ALLOWED_TRANSITIONS.get(self.status, frozenset())
