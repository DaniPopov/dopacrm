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
    """POST /api/v1/tenants — onboard a new gym.

    Only ``slug`` and ``name`` are required. Everything else is optional
    and can be filled in later via PATCH.
    """

    # Identity (required)
    slug: str = Field(min_length=2, max_length=50, description="URL-safe identifier (unique)")
    name: str = Field(min_length=1, max_length=200, description="Display name of the gym")

    # Branding
    logo_url: str | None = Field(default=None, description="S3 key from /uploads/logo")

    # Contact
    phone: str | None = None
    email: str | None = Field(default=None, description="Business email for notifications")
    website: str | None = None

    # Address
    address_street: str | None = None
    address_city: str | None = None
    address_country: str | None = Field(default="IL", description="ISO 3166-1 alpha-2")
    address_postal_code: str | None = None

    # Legal
    legal_name: str | None = Field(default=None, description="Legal business name")
    tax_id: str | None = Field(default=None, description="ח.פ / ע.מ")

    # Regional
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
                    "email": "info@ironfit.co.il",
                    "website": "https://ironfit.co.il",
                    "address_street": "Rothschild 1",
                    "address_city": "Tel Aviv",
                    "address_country": "IL",
                    "address_postal_code": "6578901",
                    "legal_name": "IronFit Ltd",
                    "tax_id": "123456789",
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
    logo_url: str | None = None
    email: str | None = None
    website: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_country: str | None = None
    address_postal_code: str | None = None
    legal_name: str | None = None
    tax_id: str | None = None
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
    status: TenantStatus
    saas_plan_id: UUID

    # Branding
    logo_url: str | None
    logo_presigned_url: str | None = Field(
        default=None,
        description="Short-lived presigned URL to the logo (1 hour). Null if no logo.",
    )

    # Contact
    phone: str | None
    email: str | None
    website: str | None

    # Address
    address_street: str | None
    address_city: str | None
    address_country: str | None
    address_postal_code: str | None

    # Legal
    legal_name: str | None
    tax_id: str | None

    # Regional
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
                    "status": "trial",
                    "saas_plan_id": "aaaa0000-0000-0000-0000-000000000000",
                    "logo_url": None,
                    "phone": "+972-3-555-1234",
                    "email": "info@ironfit.co.il",
                    "website": "https://ironfit.co.il",
                    "address_street": "Rothschild 1",
                    "address_city": "Tel Aviv",
                    "address_country": "IL",
                    "address_postal_code": "6578901",
                    "legal_name": "IronFit Ltd",
                    "tax_id": "123456789",
                    "timezone": "Asia/Jerusalem",
                    "currency": "ILS",
                    "locale": "he-IL",
                    "trial_ends_at": "2026-04-25T12:00:00+03:00",
                    "created_at": "2026-04-11T12:00:00+03:00",
                    "updated_at": "2026-04-11T12:00:00+03:00",
                }
            ]
        }
    }
