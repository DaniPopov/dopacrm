"""Pydantic domain entity for gym members.

Members are the gym's paying customers. They don't log in — no password,
no users row. The membership lifecycle lives here as a state machine:

    active ──(freeze)──> frozen ──(unfreeze)──> active
        │                  │
        └──(cancel)────────┴──> cancelled    (terminal)
        │
        └──(expire by job)─────> expired     (no active subscription)

Status transitions are enforced as pure methods on the entity
(``can_freeze``, ``can_unfreeze``, ``can_cancel``). The service calls them
before mutating — keeps business rules out of SQL.

Notable fields:
- ``custom_fields`` is free-form JSONB, only for per-tenant ad-hoc data
  (belt color, injury notes, referral source). Structured data (class
  passes, attendance, payments) lives in its own relational tables.
- ``gender`` is intentionally free text, not an enum — different gyms
  use different options. See the flexibility thesis in docs/spec.md §1.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemberStatus(StrEnum):
    """Lifecycle status of a member."""

    ACTIVE = "active"
    FROZEN = "frozen"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Member(BaseModel):
    """A gym member — the core entity of the CRM."""

    id: UUID
    tenant_id: UUID = Field(description="Gym this member belongs to. Every query scopes by this.")

    # Required identity + contact
    first_name: str
    last_name: str
    phone: str = Field(description="Primary contact. Unique within tenant.")

    # Optional personal info
    email: str | None = None
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, description="Free text — owner-configurable later.")

    # Lifecycle
    status: MemberStatus = MemberStatus.ACTIVE
    join_date: date
    frozen_at: date | None = None
    frozen_until: date | None = None
    cancelled_at: date | None = None

    notes: str | None = None
    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Ad-hoc per-tenant data. Do not query on this.",
    )

    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        """Best-effort display name."""
        return f"{self.first_name} {self.last_name}".strip()

    def is_active(self) -> bool:
        return self.status == MemberStatus.ACTIVE

    def can_freeze(self) -> bool:
        """Only active members can be frozen."""
        return self.status == MemberStatus.ACTIVE

    def can_unfreeze(self) -> bool:
        """Only frozen members can be unfrozen."""
        return self.status == MemberStatus.FROZEN

    def can_cancel(self) -> bool:
        """Cancel is idempotent-ish — only blocks if already cancelled."""
        return self.status != MemberStatus.CANCELLED
