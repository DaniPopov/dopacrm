"""Request/response schemas for the Schedule API."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.entities.class_coach import WEEKDAYS
from app.domain.entities.class_session import SessionStatus


# ── Templates ─────────────────────────────────────────────────────────


class CreateTemplateRequest(BaseModel):
    """POST /api/v1/schedule/templates — add a recurring rule (owner+)."""

    class_id: UUID
    weekdays: list[str] = Field(min_length=1)
    start_time: time
    end_time: time
    head_coach_id: UUID
    assistant_coach_id: UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[str]) -> list[str]:
        for w in v:
            if w not in WEEKDAYS:
                msg = f"invalid weekday code: {w!r}"
                raise ValueError(msg)
        if len(set(v)) != len(v):
            msg = "duplicate weekday codes"
            raise ValueError(msg)
        return v


class UpdateTemplateRequest(BaseModel):
    """PATCH /api/v1/schedule/templates/{id} (owner+)."""

    weekdays: list[str] | None = Field(default=None)
    start_time: time | None = None
    end_time: time | None = None
    head_coach_id: UUID | None = None
    assistant_coach_id: UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool | None = None

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) == 0:
            msg = "weekdays cannot be empty"
            raise ValueError(msg)
        for w in v:
            if w not in WEEKDAYS:
                msg = f"invalid weekday code: {w!r}"
                raise ValueError(msg)
        if len(set(v)) != len(v):
            msg = "duplicate weekday codes"
            raise ValueError(msg)
        return v


class TemplateResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    weekdays: list[str]
    start_time: time
    end_time: time
    head_coach_id: UUID
    assistant_coach_id: UUID | None
    starts_on: date
    ends_on: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Sessions ──────────────────────────────────────────────────────────


class CreateAdHocSessionRequest(BaseModel):
    """POST /api/v1/schedule/sessions — one-off session (owner+)."""

    class_id: UUID
    starts_at: datetime
    ends_at: datetime
    head_coach_id: UUID | None = None
    assistant_coach_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=500)


class UpdateSessionRequest(BaseModel):
    """PATCH /api/v1/schedule/sessions/{id} (owner+)."""

    head_coach_id: UUID | None = None
    assistant_coach_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


class CancelSessionRequest(BaseModel):
    """POST /api/v1/schedule/sessions/{id}/cancel."""

    reason: str | None = Field(default=None, max_length=500)


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    template_id: UUID | None
    starts_at: datetime
    ends_at: datetime
    head_coach_id: UUID | None
    assistant_coach_id: UUID | None
    status: SessionStatus
    is_customized: bool
    cancelled_at: datetime | None
    cancelled_by: UUID | None
    cancellation_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ── Bulk action ───────────────────────────────────────────────────────


class BulkActionRequest(BaseModel):
    """POST /api/v1/schedule/bulk-action (owner+).

    Owner-friendly "apply to every session of this class in this date
    range." Action = cancel | swap_coach.
    """

    class_id: UUID
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    action: Literal["cancel", "swap_coach"]
    new_coach_id: UUID | None = Field(
        default=None,
        description="Required when action='swap_coach'.",
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Used for cancel's audit note.",
    )

    model_config = {"populate_by_name": True}


class BulkActionResponse(BaseModel):
    action: str
    affected_ids: list[UUID]
    cancelled_count: int
    swapped_count: int


# ── Tenant features ───────────────────────────────────────────────────


class UpdateTenantFeaturesRequest(BaseModel):
    """PATCH /api/v1/tenants/{id}/features — super_admin only.

    Partial merge into ``tenants.features_enabled``. Keys not listed
    are left unchanged; explicit False disables a feature.
    """

    coaches: bool | None = None
    schedule: bool | None = None

    def to_update_dict(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        if self.coaches is not None:
            out["coaches"] = self.coaches
        if self.schedule is not None:
            out["schedule"] = self.schedule
        return out


class TenantFeaturesResponse(BaseModel):
    features_enabled: dict[str, bool]
