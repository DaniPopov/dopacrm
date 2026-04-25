"""Request/response schemas for the Tenants API.

Each schema has ``json_schema_extra`` so Swagger's "Try it out" button
shows a realistic pre-filled example.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.entities.tenant import TenantStatus

# Lowercase English letters + digits, separated by single hyphens.
# Cannot start or end with hyphen. Cannot have consecutive hyphens.
# Examples OK: "ironfit-tlv", "gym1", "crossfit-rosh-haayin"
# Examples bad: "IronFit-TLV" (uppercase), "gym_1" (underscore), "-gym" (leading hyphen),
#               "gym--pro" (double hyphen), "חדר" (Hebrew)
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Machine-readable error code embedded in the validation message. The
# frontend `humanizeTenantError` picks it up and swaps in a Hebrew
# message. Keep this exact string in sync with frontend/src/lib/api-errors.ts.
SLUG_INVALID_ERROR_CODE = "slug_invalid_format"


class CreateTenantRequest(BaseModel):
    """POST /api/v1/tenants — onboard a new gym.

    Only ``slug`` and ``name`` are required. Everything else is optional
    and can be filled in later via PATCH.
    """

    # Identity (required)
    slug: str = Field(
        min_length=2,
        max_length=64,
        description=(
            "URL-safe identifier (unique). Lowercase English letters, digits, "
            "and hyphens only — no spaces, uppercase, or non-Latin characters."
        ),
    )
    name: str = Field(min_length=1, max_length=200, description="Display name of the gym")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not SLUG_PATTERN.match(v):
            raise ValueError(SLUG_INVALID_ERROR_CODE)
        return v

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
                    "slug": "dopamineogym-or-yheuda",
                    "name": "דופמינו ג׳ים",
                    "phone": "0543123090",
                    "email": "mark@dopamineogym.com",
                    "website": "https://dopamineo.co.il/",
                    "address_street": "יוני נתניהו 5",
                    "address_city": "אור יהודה",
                    "address_country": "IL",
                    "address_postal_code": "6578901",
                    "legal_name": "דופמינו בע״מ",
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
                    "name": "דופמינו ג׳ים — אור יהודה",
                    "phone": "0543123090",
                }
            ]
        }
    }


class TenantStatsResponse(BaseModel):
    """Per-tenant counters shown on the tenant detail page."""

    total_members: int
    active_members: int
    total_users: int

    model_config = {
        "json_schema_extra": {
            "examples": [{"total_members": 42, "active_members": 38, "total_users": 5}]
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

    # Per-tenant feature gates. Missing key = OFF. See
    # docs/features/feature-flags.md.
    features_enabled: dict[str, bool] = Field(default_factory=dict)

    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "slug": "dopamineogym-or-yheuda",
                    "name": "דופמינו ג׳ים",
                    "status": "trial",
                    "saas_plan_id": "aaaa0000-0000-0000-0000-000000000000",
                    "logo_url": None,
                    "phone": "0543123090",
                    "email": "mark@dopamineogym.com",
                    "website": "https://dopamineo.co.il/",
                    "address_street": "יוני נתניהו 5",
                    "address_city": "אור יהודה",
                    "address_country": "IL",
                    "address_postal_code": "6578901",
                    "legal_name": "דופמינו בע״מ",
                    "tax_id": "123456789",
                    "timezone": "Asia/Jerusalem",
                    "currency": "ILS",
                    "locale": "he-IL",
                    "trial_ends_at": "2026-04-29T12:00:00+03:00",
                    "created_at": "2026-04-15T12:00:00+03:00",
                    "updated_at": "2026-04-15T12:00:00+03:00",
                }
            ]
        }
    }
