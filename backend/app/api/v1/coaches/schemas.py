"""Pydantic request/response schemas for the Coaches API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.entities.class_coach import WEEKDAYS, PayModel
from app.domain.entities.coach import CoachStatus


# ── Coach ─────────────────────────────────────────────────────────────


class CreateCoachRequest(BaseModel):
    """POST /api/v1/coaches — add a coach to the caller's tenant."""

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    user_id: UUID | None = Field(
        default=None,
        description="Optional existing user to link. Must be in the caller's tenant.",
    )
    hired_at: date | None = None
    custom_attrs: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "first_name": "David",
                    "last_name": "Cohen",
                    "phone": "+972-50-123-4567",
                    "email": "david@gym.com",
                }
            ]
        }
    }


class UpdateCoachRequest(BaseModel):
    """PATCH /api/v1/coaches/{id} — partial update (owner+)."""

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    custom_attrs: dict[str, Any] | None = None


class InviteCoachUserRequest(BaseModel):
    """POST /api/v1/coaches/{id}/invite-user — create a login for the coach."""

    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters.")


class CoachResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None
    first_name: str
    last_name: str
    phone: str | None
    email: str | None
    hired_at: date
    status: CoachStatus
    frozen_at: datetime | None
    cancelled_at: datetime | None
    custom_attrs: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Class-coach links ─────────────────────────────────────────────────


class AssignCoachRequest(BaseModel):
    """POST /api/v1/classes/{class_id}/coaches — attach a coach to a class."""

    coach_id: UUID
    role: str = Field(default="ראשי", min_length=1, max_length=40)
    is_primary: bool = False
    pay_model: PayModel
    pay_amount_cents: int = Field(ge=0)
    weekdays: list[str] = Field(
        default_factory=list,
        description="Lowercase 3-letter codes ('sun'..'sat'). Empty = all days.",
    )
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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coach_id": "11111111-1111-1111-1111-111111111111",
                    "role": "ראשי",
                    "is_primary": True,
                    "pay_model": "per_attendance",
                    "pay_amount_cents": 5000,
                    "weekdays": ["sun", "tue"],
                }
            ]
        }
    }


class UpdateClassCoachRequest(BaseModel):
    """PATCH /api/v1/class-coaches/{link_id} — edit a link (owner+)."""

    role: str | None = Field(default=None, min_length=1, max_length=40)
    is_primary: bool | None = None
    pay_model: PayModel | None = None
    pay_amount_cents: int | None = Field(default=None, ge=0)
    weekdays: list[str] | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for w in v:
            if w not in WEEKDAYS:
                msg = f"invalid weekday code: {w!r}"
                raise ValueError(msg)
        if len(set(v)) != len(v):
            msg = "duplicate weekday codes"
            raise ValueError(msg)
        return v


class ClassCoachResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    coach_id: UUID
    role: str
    is_primary: bool
    pay_model: PayModel
    pay_amount_cents: int
    weekdays: list[str]
    starts_on: date
    ends_on: date | None
    created_at: datetime
    updated_at: datetime


# ── Earnings ──────────────────────────────────────────────────────────


class EarningsLinkRowResponse(BaseModel):
    class_id: UUID
    class_name: str | None
    role: str
    pay_model: PayModel
    pay_amount_cents: int
    cents: int
    unit_count: int


class EarningsBreakdownResponse(BaseModel):
    coach_id: UUID
    from_: date = Field(alias="from")
    to: date
    effective_from: date | None
    effective_to: date | None
    currency: str
    total_cents: int
    by_link: list[EarningsLinkRowResponse]
    by_class_cents: dict[UUID, int]
    by_pay_model_cents: dict[str, int]

    model_config = {"populate_by_name": True}


# ── Reassign ──────────────────────────────────────────────────────────


class ReassignCoachRequest(BaseModel):
    """POST /api/v1/attendance/{id}/reassign-coach — owner correction."""

    coach_id: UUID | None = Field(description="``null`` to clear the attribution.")
