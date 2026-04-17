"""Request/response schemas for the Attendance API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.class_entry import OverrideKind


class RecordEntryRequest(BaseModel):
    """POST /api/v1/attendance — record one check-in."""

    member_id: UUID
    class_id: UUID
    override: bool = Field(
        default=False,
        description=(
            "Set to true to bypass quota-exceeded or not-covered guards. "
            "The UI shows a confirmation modal + sets this on retry."
        ),
    )
    override_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Free text — only recorded when override=true.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "member_id": "11111111-1111-1111-1111-111111111111",
                    "class_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        }
    }


class UndoEntryRequest(BaseModel):
    """POST /api/v1/attendance/{id}/undo — soft-delete within 24h."""

    reason: str | None = Field(default=None, max_length=500)


class QuotaCheckResponse(BaseModel):
    """Result of the quota peek — used by the check-in page to color
    class cards before staff taps one."""

    allowed: bool
    remaining: int | None = None
    used: int | None = None
    quantity: int | None = None
    reset_period: str | None = None
    reason: str | None = None


class EntryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    subscription_id: UUID
    class_id: UUID
    entered_at: datetime
    entered_by: UUID | None
    undone_at: datetime | None
    undone_by: UUID | None
    undone_reason: str | None
    override: bool
    override_kind: OverrideKind | None
    override_reason: str | None


class SummaryItem(BaseModel):
    """One row in the member's entitlement-usage summary."""

    allowed: bool
    remaining: int | None
    used: int | None
    quantity: int | None
    reset_period: str | None
    reason: str | None


class AttendanceListResponse(BaseModel):
    """Wrapper for list endpoints — leaves room to add pagination metadata later."""

    entries: list[EntryResponse]
