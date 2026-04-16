"""Request/response schemas for the Classes API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateGymClassRequest(BaseModel):
    """POST /api/v1/classes — create a class in the caller's tenant."""

    name: str = Field(min_length=1, max_length=100, description="Unique within tenant")
    description: str | None = None
    color: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Hex code (e.g. '#3B82F6'). Frontend offers a preset palette + "
            "free-picker fallback so owners don't have to type hex codes. "
            "Backend accepts any string up to 20 chars — the UI is "
            "responsible for sending a valid value."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "ספינינג",
                    "description": "שיעור רכיבה על אופני כושר בקצב גבוה",
                    "color": "#3B82F6",
                }
            ]
        }
    }


class UpdateGymClassRequest(BaseModel):
    """PATCH /api/v1/classes/{id} — partial update."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"description": "עודכן — כולל חימום ממושך יותר", "color": "#10B981"}
            ]
        }
    }


class GymClassResponse(BaseModel):
    """Standard gym class response shape."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    color: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "ספינינג",
                    "description": "שיעור רכיבה על אופני כושר בקצב גבוה",
                    "color": "#3B82F6",
                    "is_active": True,
                    "created_at": "2026-04-16T10:00:00+03:00",
                    "updated_at": "2026-04-16T10:00:00+03:00",
                }
            ]
        }
    }
