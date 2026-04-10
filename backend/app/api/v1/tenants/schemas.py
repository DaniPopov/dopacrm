"""Request/response schemas for the Tenants API.

Each schema has ``json_schema_extra`` so Swagger's "Try it out" button
shows a realistic pre-filled example.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.tenant import TenantStatus


class CreateTenantRequest(BaseModel):
    """POST /api/v1/tenants — onboard a new gym."""

    slug: str = Field(min_length=2, max_length=50, description="URL-safe identifier (unique)")
    name: str = Field(min_length=1, max_length=200, description="Display name of the gym")
    phone: str | None = None
    timezone: str = Field(default="Asia/Jerusalem", description="IANA timezone")
    currency: str = Field(default="ILS", description="ISO 4217 currency code")
    locale: str = Field(default="he-IL", description="BCP 47 locale")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "slug": "ironfit-tlv",
                    "name": "IronFit Tel Aviv",
                    "phone": "+972-3-555-1234",
                    "timezone": "Asia/Jerusalem",
                    "currency": "ILS",
                    "locale": "he-IL",
                }
            ]
        }
    }


class UpdateTenantRequest(BaseModel):
    """PATCH /api/v1/tenants/{tenant_id} — partial update."""

    name: str | None = None
    phone: str | None = None
    timezone: str | None = None
    currency: str | None = None
    locale: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "IronFit Tel Aviv — Rothschild",
                    "phone": "+972-3-555-9999",
                }
            ]
        }
    }


class TenantResponse(BaseModel):
    """Standard tenant response."""

    id: UUID
    slug: str
    name: str
    phone: str | None
    status: TenantStatus
    timezone: str
    currency: str
    locale: str
    trial_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "slug": "ironfit-tlv",
                    "name": "IronFit Tel Aviv",
                    "phone": "+972-3-555-1234",
                    "status": "active",
                    "timezone": "Asia/Jerusalem",
                    "currency": "ILS",
                    "locale": "he-IL",
                    "trial_ends_at": None,
                    "created_at": "2026-04-10T12:00:00+03:00",
                    "updated_at": "2026-04-10T12:00:00+03:00",
                }
            ]
        }
    }
