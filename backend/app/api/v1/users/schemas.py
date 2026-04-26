"""Request/response schemas for the Users API.

Each schema has ``json_schema_extra`` so Swagger's "Try it out" button
shows a realistic pre-filled example.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.domain.entities.user import Role


class CreateUserRequest(BaseModel):
    """POST /api/v1/users — create a new user."""

    email: EmailStr
    password: str | None = Field(
        default=None,
        min_length=8,
        description="Minimum 8 characters.",
    )

    role: Role
    tenant_id: UUID | None = Field(
        default=None, description="Required for owner/staff/sales. Null for super_admin."
    )
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    oauth_provider: str | None = None
    oauth_id: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "owner@dopagym.com",
                    "password": "SecureP@ss123",
                    "role": "owner",
                    "first_name": "Dana",
                    "last_name": "Cohen",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                }
            ]
        }
    }


class UpdateUserRequest(BaseModel):
    """PATCH /api/v1/users/{user_id} — partial update.

    super_admin can reset a user's password by including ``password`` here.
    Plaintext is hashed with argon2 in the service layer; it never touches
    the DB directly. Leave blank / omit to keep the existing password.
    """

    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    password: str | None = Field(
        default=None,
        min_length=8,
        description="New password. Minimum 8 characters.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "staff",
                    "is_active": True,
                    "first_name": "Dana",
                    "last_name": "Cohen",
                }
            ]
        }
    }


class UserResponse(BaseModel):
    """Standard user response — never includes password_hash."""

    id: UUID
    email: str
    role: Role
    tenant_id: UUID | None
    is_active: bool
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    oauth_provider: str | None
    # Per-tenant feature flags. Populated by ``/auth/me`` so the frontend
    # can gate sidebar / route visibility without a second round-trip.
    # Other user-returning endpoints leave this empty.
    tenant_features_enabled: dict[str, bool] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "bb22240d-f00d-47fc-ac60-aa5b08f550aa",
                    "email": "owner@dopagym.com",
                    "role": "owner",
                    "first_name": "Dana",
                    "last_name": "Cohen",
                    "phone": "+972-50-123-4567",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "is_active": True,
                    "oauth_provider": None,
                    "created_at": "2026-04-09T12:00:00+03:00",
                    "updated_at": "2026-04-09T12:00:00+03:00",
                }
            ]
        }
    }
