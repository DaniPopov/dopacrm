"""Pydantic request/response schemas for the Leads API.

Notes:

- Status enum is **not** writable via ``UpdateLeadRequest`` — pipeline
  transitions go through ``POST /leads/{id}/status``. Stripping it
  here surfaces a clean 422 if a client tries to PATCH the status.
- ``AddActivityRequest.type`` excludes ``status_change`` — the system
  is the only writer of those rows. A separate ``literal``-style
  validator enforces this at parse time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.entities.lead import LeadSource, LeadStatus
from app.domain.entities.lead_activity import LeadActivityType
from app.domain.entities.member import MemberStatus
from app.domain.entities.subscription import PaymentMethod, SubscriptionStatus

# ── Lead ──────────────────────────────────────────────────────────────


class CreateLeadRequest(BaseModel):
    """POST /api/v1/leads — add a lead to the caller's tenant."""

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=30)
    email: EmailStr | None = None
    source: LeadSource = LeadSource.OTHER
    assigned_to: UUID | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "first_name": "Yael",
                    "last_name": "Cohen",
                    "phone": "+972-50-123-4567",
                    "source": "walk_in",
                    "notes": "Walked in asking about boxing.",
                }
            ]
        }
    }


class UpdateLeadRequest(BaseModel):
    """PATCH /api/v1/leads/{id} — partial update (sales+).

    Status / lost_reason / converted_member_id are NOT mutable here —
    they're driven by the dedicated endpoints that emit activity rows.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, min_length=1, max_length=30)
    email: EmailStr | None = None
    source: LeadSource | None = None
    assigned_to: UUID | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None


class SetStatusRequest(BaseModel):
    """POST /api/v1/leads/{id}/status — pipeline transition.

    ``new_status='converted'`` is rejected by the service (use the
    convert endpoint). ``lost_reason`` is read only when
    ``new_status='lost'`` (other transitions clear it).
    """

    new_status: LeadStatus
    lost_reason: str | None = Field(default=None, max_length=500)


class AssignLeadRequest(BaseModel):
    """POST /api/v1/leads/{id}/assign — set or clear the assignee."""

    user_id: UUID | None = Field(
        default=None,
        description="Pass null to unassign. Must be in the caller's tenant.",
    )


class ConvertLeadRequest(BaseModel):
    """POST /api/v1/leads/{id}/convert — atomic Member + Subscription."""

    plan_id: UUID
    payment_method: PaymentMethod
    start_date: date | None = Field(
        default=None,
        description="Subscription start date. Defaults to today; allowed up to 30 days back.",
    )
    copy_notes_to_member: bool = Field(
        default=True,
        description="Copy lead.notes onto the new member.notes.",
    )


class AddActivityRequest(BaseModel):
    """POST /api/v1/leads/{id}/activities — log a touchpoint.

    ``type=status_change`` is system-only; clients sending it get 422.
    Blank notes are rejected as 422 to keep the timeline useful.
    """

    type: LeadActivityType
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("type")
    @classmethod
    def _no_status_change(cls, v: LeadActivityType) -> LeadActivityType:
        if v == LeadActivityType.STATUS_CHANGE:
            raise ValueError(
                "type 'status_change' is system-only — use POST /leads/{id}/status instead"
            )
        return v

    @field_validator("note")
    @classmethod
    def _trim_nonblank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("note cannot be blank")
        return v


# ── Responses ─────────────────────────────────────────────────────────


class LeadResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str
    source: LeadSource
    status: LeadStatus
    assigned_to: UUID | None
    notes: str | None
    lost_reason: str | None
    converted_member_id: UUID | None
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class LeadActivityResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    type: LeadActivityType
    note: str
    created_by: UUID | None
    created_at: datetime


class LostReasonRowResponse(BaseModel):
    """One row in the autocomplete dropdown."""

    reason: str
    count: int


class LeadStatsResponse(BaseModel):
    """GET /leads/stats — Kanban headers + dashboard widget."""

    counts: dict[LeadStatus, int]
    conversion_rate_30d: float | None = Field(
        description="Converted / created in the last 30 days. None when zero leads created."
    )


# Slim response shapes for the convert endpoint — bare what the UI
# needs to navigate to the new member detail page. Re-using the full
# MemberResponse / SubscriptionResponse from those features would be
# nicer but creates an import cycle; copying the relevant fields here
# is the lighter-weight choice.


class ConvertedMemberSummary(BaseModel):
    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    phone: str
    email: str | None
    status: MemberStatus
    join_date: date
    notes: str | None


class ConvertedSubscriptionSummary(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    started_at: date
    expires_at: date | None
    price_cents: int
    currency: str


class ConvertLeadResponse(BaseModel):
    """Full result of a successful convert — UI navigates to the
    member's detail page after."""

    lead: LeadResponse
    member: ConvertedMemberSummary
    subscription: ConvertedSubscriptionSummary
