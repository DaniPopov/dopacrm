"""Request/response schemas for the Members API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.member import MemberStatus


class CreateMemberRequest(BaseModel):
    """POST /api/v1/members — create a new member in the caller's tenant.

    ``first_name``, ``last_name``, and ``phone`` are required.
    ``join_date`` defaults to today (server-side) when omitted.
    """

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=3, max_length=30, description="Unique within tenant")
    email: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=50)
    join_date: date | None = Field(default=None, description="Defaults to today if omitted")
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Ad-hoc per-tenant data. Do not put structured queryable data here.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "first_name": "Dana",
                    "last_name": "Cohen",
                    "phone": "+972-50-123-4567",
                    "email": "dana@example.com",
                    "gender": "female",
                    "custom_fields": {"referral_source": "walk_in"},
                }
            ]
        }
    }


class UpdateMemberRequest(BaseModel):
    """PATCH /api/v1/members/{id} — partial update. All fields optional."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{"phone": "+972-52-999-0000", "notes": "Moved to morning sessions"}]
        }
    }


class FreezeMemberRequest(BaseModel):
    """POST /api/v1/members/{id}/freeze — optional body."""

    until: date | None = Field(
        default=None,
        description="Optional auto-unfreeze date. Null means indefinite freeze.",
    )


class MemberResponse(BaseModel):
    """Standard member response shape."""

    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    phone: str
    email: str | None
    date_of_birth: date | None
    gender: str | None
    status: MemberStatus
    join_date: date
    frozen_at: date | None
    frozen_until: date | None
    cancelled_at: date | None
    notes: str | None
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "first_name": "Dana",
                    "last_name": "Cohen",
                    "phone": "+972-50-123-4567",
                    "email": "dana@example.com",
                    "date_of_birth": "1990-05-15",
                    "gender": "female",
                    "status": "active",
                    "join_date": "2026-04-14",
                    "frozen_at": None,
                    "frozen_until": None,
                    "cancelled_at": None,
                    "notes": None,
                    "custom_fields": {"referral_source": "walk_in"},
                    "created_at": "2026-04-14T12:00:00+03:00",
                    "updated_at": "2026-04-14T12:00:00+03:00",
                }
            ]
        }
    }
