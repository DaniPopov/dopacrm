"""Request/response schemas for the Subscriptions API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.subscription import (
    PaymentMethod,
    SubscriptionEventType,
    SubscriptionStatus,
)

# ── Create / enrollment ──────────────────────────────────────────────────────


class CreateSubscriptionRequest(BaseModel):
    """POST /api/v1/subscriptions — enroll a member in a plan."""

    member_id: UUID
    plan_id: UUID
    started_at: date | None = Field(
        default=None,
        description="Defaults to today. Future dates allowed ('starts Monday').",
    )
    expires_at: date | None = Field(
        default=None,
        description=(
            "Cash / prepaid: set to next payment due date. "
            "Card-auto: leave null (runs until cancelled). "
            "One-time plans default to started_at + duration_days when omitted."
        ),
    )
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.CASH,
        description="How the member pays: cash / credit_card / standing_order / other.",
    )
    payment_method_detail: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Free-text elaboration. Required by the UI when method='other'; "
            "optional otherwise (e.g., 'Visa 1234')."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "member_id": "11111111-1111-1111-1111-111111111111",
                    "plan_id": "22222222-2222-2222-2222-222222222222",
                    "started_at": "2026-04-17",
                    "expires_at": "2026-05-17",
                }
            ]
        }
    }


# ── Freeze / Unfreeze / Renew / Cancel / ChangePlan ──────────────────────────


class FreezeSubscriptionRequest(BaseModel):
    """POST /api/v1/subscriptions/{id}/freeze"""

    frozen_until: date | None = Field(
        default=None,
        description=("Optional auto-unfreeze date. Null = open-ended freeze (manual only)."),
    )


class RenewSubscriptionRequest(BaseModel):
    """POST /api/v1/subscriptions/{id}/renew

    Default extension = plan's billing period (monthly=+30d, quarterly=+90d,
    yearly=+365d, one_time=+duration_days). Override via `new_expires_at`
    for "she paid 2 months upfront" and similar.

    Optional `new_payment_method` / `new_payment_method_detail` handle the
    common "member moved from cash to standing order" flow at renewal time.
    Omit both to keep the existing payment info.
    """

    new_expires_at: date | None = Field(
        default=None,
        description="Override the default billing-period extension.",
    )
    new_payment_method: PaymentMethod | None = Field(
        default=None,
        description="Optional: switch payment method at renewal time.",
    )
    new_payment_method_detail: str | None = Field(
        default=None,
        max_length=200,
        description="Paired with new_payment_method. Ignored if method is not provided.",
    )


class ChangePlanRequest(BaseModel):
    """POST /api/v1/subscriptions/{id}/change-plan

    Creates a new sub with the new plan's current price snapshot; marks
    the old sub ``replaced`` (NOT cancelled — different for reports).
    """

    new_plan_id: UUID
    effective_date: date | None = Field(
        default=None,
        description="Defaults to today. New sub's started_at.",
    )


class CancelSubscriptionRequest(BaseModel):
    """POST /api/v1/subscriptions/{id}/cancel

    HARD-terminal. Reason is a canonical dropdown key; detail is free text.
    """

    reason: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Canonical key: 'moved_away' | 'too_expensive' | 'not_using' "
            "| 'injury' | 'other'. Free text allowed but the UI emits one of these."
        ),
    )
    detail: str | None = Field(
        default=None,
        max_length=500,
        description="Optional free-text elaboration.",
    )


# ── Response shapes ──────────────────────────────────────────────────────────


class SubscriptionResponse(BaseModel):
    """Subscription as returned to the frontend."""

    id: UUID
    tenant_id: UUID
    member_id: UUID
    plan_id: UUID

    status: SubscriptionStatus
    price_cents: int
    currency: str
    payment_method: PaymentMethod
    payment_method_detail: str | None

    started_at: date
    expires_at: date | None
    frozen_at: date | None
    frozen_until: date | None
    expired_at: date | None
    cancelled_at: date | None
    cancellation_reason: str | None
    replaced_at: date | None
    replaced_by_id: UUID | None

    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "member_id": "11111111-1111-1111-1111-111111111111",
                    "plan_id": "22222222-2222-2222-2222-222222222222",
                    "status": "active",
                    "price_cents": 45000,
                    "currency": "ILS",
                    "started_at": "2026-04-01",
                    "expires_at": "2026-05-01",
                    "frozen_at": None,
                    "frozen_until": None,
                    "expired_at": None,
                    "cancelled_at": None,
                    "cancellation_reason": None,
                    "replaced_at": None,
                    "replaced_by_id": None,
                    "created_at": "2026-04-17T12:00:00+03:00",
                    "updated_at": "2026-04-17T12:00:00+03:00",
                }
            ]
        }
    }


class SubscriptionEventResponse(BaseModel):
    """Timeline entry as returned to the frontend."""

    id: UUID
    tenant_id: UUID
    subscription_id: UUID
    event_type: SubscriptionEventType
    event_data: dict[str, Any]
    occurred_at: datetime
    created_by: UUID | None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "44444444-4444-4444-4444-444444444444",
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                    "subscription_id": "33333333-3333-3333-3333-333333333333",
                    "event_type": "renewed",
                    "event_data": {
                        "days_late": 3,
                        "previous_expires_at": "2026-04-15",
                        "new_expires_at": "2026-05-18",
                    },
                    "occurred_at": "2026-04-18T12:00:00+03:00",
                    "created_by": "55555555-5555-5555-5555-555555555555",
                }
            ]
        }
    }
