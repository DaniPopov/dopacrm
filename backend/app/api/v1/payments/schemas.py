"""Pydantic request/response schemas for the Payments API.

Notes:

- ``RecordPaymentRequest.amount_cents`` is **positive**; refunds go
  through their own endpoint that flips the sign server-side.
- ``RefundPaymentRequest.amount_cents`` is also positive (the user
  enters "10 ₪", not "-10 ₪"); the service negates before insert.
- No ``UpdatePaymentRequest`` — payments are append-only.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.subscription import PaymentMethod


class RecordPaymentRequest(BaseModel):
    """POST /api/v1/payments — record a collected payment (staff+)."""

    member_id: UUID
    amount_cents: int = Field(gt=0, description="Positive integer (cents).")
    payment_method: PaymentMethod
    paid_at: date | None = Field(
        default=None,
        description="Defaults to today. Future dates rejected.",
    )
    subscription_id: UUID | None = Field(
        default=None,
        description=(
            "Optional. If set, must belong to the same member. Drop-ins / "
            "one-off payments leave this null."
        ),
    )
    notes: str | None = Field(default=None, max_length=2000)
    external_ref: str | None = Field(
        default=None,
        max_length=200,
        description="Reserved for Phase 5 processor integrations.",
    )
    backdate: bool = Field(
        default=False,
        description=(
            "Set True to allow paid_at more than 30 days in the past. Small friction against typos."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "member_id": "...",
                    "amount_cents": 25000,
                    "payment_method": "cash",
                    "paid_at": "2026-04-30",
                    "subscription_id": "...",
                    "notes": "April monthly fee",
                }
            ]
        }
    }


class RefundPaymentRequest(BaseModel):
    """POST /api/v1/payments/{id}/refund — record a refund (owner+).

    ``amount_cents`` is positive (the system flips the sign on insert).
    Omit for full refund of the remaining refundable amount.
    """

    amount_cents: int | None = Field(
        default=None,
        gt=0,
        description="Positive cents. Omit to refund the remaining amount in full.",
    )
    reason: str | None = Field(default=None, max_length=500)


class PaymentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    subscription_id: UUID | None
    amount_cents: int
    currency: str
    payment_method: PaymentMethod
    paid_at: date
    notes: str | None
    refund_of_payment_id: UUID | None
    external_ref: str | None
    recorded_by: UUID | None
    created_at: datetime


# ── Dashboard summary ────────────────────────────────────────────────


class RangeRevenueResponse(BaseModel):
    """One bucket — this month, last month, etc."""

    paid_from: date
    paid_to: date
    cents: int


class PlanRevenueRowResponse(BaseModel):
    plan_id: UUID
    cents: int


class RevenueSummaryResponse(BaseModel):
    """GET /api/v1/dashboard/revenue — drives the GymDashboard widgets."""

    currency: str
    this_month: RangeRevenueResponse
    last_month: RangeRevenueResponse
    mom_pct: float | None = Field(
        description=(
            "Month-over-month change. None when last_month is zero "
            "(avoids divide-by-zero on a tenant's first month)."
        ),
    )
    by_plan: list[PlanRevenueRowResponse]
    by_method: dict[str, int]
    arpm_cents: int
