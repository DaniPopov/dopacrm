"""Request/response schemas for the Membership Plans API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.membership_plan import (
    BillingPeriod,
    PlanType,
    ResetPeriod,
)

# ── Entitlement shapes (used inside plan create/update/response) ─────────────


class EntitlementInputSchema(BaseModel):
    """One entitlement rule in a plan."""

    class_id: UUID | None = Field(
        default=None,
        description="FK to classes.id in the same tenant. Null = 'any class'.",
    )
    quantity: int | None = Field(
        default=None,
        description=(
            "How many entries. Must be NULL when reset_period='unlimited'; required otherwise."
        ),
    )
    reset_period: ResetPeriod


class EntitlementResponseSchema(BaseModel):
    """Entitlement as returned to the frontend."""

    id: UUID
    plan_id: UUID
    class_id: UUID | None
    quantity: int | None
    reset_period: ResetPeriod
    created_at: datetime


# ── Plan shapes ──────────────────────────────────────────────────────────────


class CreatePlanRequest(BaseModel):
    """POST /api/v1/plans — create a plan in the caller's tenant."""

    name: str = Field(min_length=1, max_length=100, description="Unique within tenant")
    description: str | None = None
    type: PlanType
    price_cents: int = Field(ge=0)
    currency: str = Field(default="ILS", max_length=10)
    billing_period: BillingPeriod
    duration_days: int | None = Field(
        default=None,
        gt=0,
        description="Required for one_time plans; NULL for recurring.",
    )
    custom_attrs: dict[str, Any] = Field(default_factory=dict)
    entitlements: list[EntitlementInputSchema] = Field(
        default_factory=list,
        description=(
            "Access rules. Empty list = unlimited any class. "
            "Otherwise each rule specifies a class (or null=any) + quota + reset cadence."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "חודשי — 3 קבוצתי + 1 אישי",
                    "description": "3 שיעורים קבוצתיים + אימון אישי אחד בשבוע",
                    "type": "recurring",
                    "price_cents": 45000,
                    "currency": "ILS",
                    "billing_period": "monthly",
                    "entitlements": [
                        {
                            "class_id": None,
                            "quantity": 3,
                            "reset_period": "weekly",
                        }
                    ],
                }
            ]
        }
    }


class UpdatePlanRequest(BaseModel):
    """PATCH /api/v1/plans/{id} — partial update.

    Omitting ``entitlements`` leaves existing rules untouched.
    Passing ``entitlements: []`` clears all rules (plan becomes
    unlimited any-class). Passing a list REPLACES the full set.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    type: PlanType | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    billing_period: BillingPeriod | None = None
    duration_days: int | None = Field(default=None, gt=0)
    custom_attrs: dict[str, Any] | None = None
    entitlements: list[EntitlementInputSchema] | None = Field(
        default=None,
        description="None leaves existing entitlements; a list REPLACES them.",
    )

    model_config = {
        "json_schema_extra": {"examples": [{"price_cents": 50000, "description": "עודכן"}]}
    }


class PlanResponse(BaseModel):
    """Plan as returned to the frontend, with entitlements eager-loaded."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    type: PlanType
    price_cents: int
    currency: str
    billing_period: BillingPeriod
    duration_days: int | None
    is_active: bool
    custom_attrs: dict[str, Any]
    entitlements: list[EntitlementResponseSchema]
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "חודשי — 3 קבוצתי + 1 אישי",
                    "description": "3 שיעורים קבוצתיים + אימון אישי אחד בשבוע",
                    "type": "recurring",
                    "price_cents": 45000,
                    "currency": "ILS",
                    "billing_period": "monthly",
                    "duration_days": None,
                    "is_active": True,
                    "custom_attrs": {},
                    "entitlements": [
                        {
                            "id": "33333333-3333-3333-3333-333333333333",
                            "plan_id": "22222222-2222-2222-2222-222222222222",
                            "class_id": None,
                            "quantity": 3,
                            "reset_period": "weekly",
                            "created_at": "2026-04-16T12:00:00+03:00",
                        }
                    ],
                    "created_at": "2026-04-16T12:00:00+03:00",
                    "updated_at": "2026-04-16T12:00:00+03:00",
                }
            ]
        }
    }
