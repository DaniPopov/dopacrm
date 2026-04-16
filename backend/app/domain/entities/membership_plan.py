"""Pydantic domain entities for MembershipPlan and PlanEntitlement.

A Membership Plan is a product the gym sells ("Monthly Unlimited",
"10-class pack", "3 group + 1 PT weekly"). Plans are per-tenant and
owner-configurable.

Entitlements encode class-access rules. A plan with zero entitlements
grants unlimited access to any class (the simple "Monthly Unlimited"
case). One or more entitlement rows makes the plan metered:

    {class_id: group, quantity: 3, reset: weekly}
    + {class_id: pt,  quantity: 1, reset: weekly}
    = "3 group + 1 PT per week"

class_id = None means "any class". reset_period = UNLIMITED with
quantity = None means "unlimited for this class type" (e.g., unlimited
yoga only).

Enforcement of quotas (counting down at check-in) lives in the future
Attendance feature. Today Plans describes the rules; tomorrow
Attendance reads them.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PlanType(StrEnum):
    """Recurring billing vs one-shot purchase."""

    RECURRING = "recurring"  # billed every billing_period until cancelled
    ONE_TIME = "one_time"  # single charge, optional duration_days expiry


class BillingPeriod(StrEnum):
    """How often the plan bills."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ONE_TIME = "one_time"  # used with PlanType.ONE_TIME


class ResetPeriod(StrEnum):
    """How often an entitlement quota resets."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    BILLING_PERIOD = "billing_period"  # resets when the subscription renews
    NEVER = "never"  # e.g., 10-class punch card with no expiry
    UNLIMITED = "unlimited"  # no quota — quantity must be None


class PlanEntitlement(BaseModel):
    """A single access rule in a plan's catalog of entitlements."""

    id: UUID
    plan_id: UUID
    class_id: UUID | None = Field(
        default=None,
        description="FK into classes. None = 'any class'.",
    )
    quantity: int | None = Field(
        default=None,
        description="How many entries. None iff reset_period = UNLIMITED.",
    )
    reset_period: ResetPeriod
    created_at: datetime

    def is_unlimited(self) -> bool:
        """True for unlimited access rules (no quota)."""
        return self.reset_period == ResetPeriod.UNLIMITED

    def applies_to_any_class(self) -> bool:
        """True if this rule is class-agnostic (class_id is None)."""
        return self.class_id is None


class MembershipPlan(BaseModel):
    """A product in the gym's catalog."""

    id: UUID
    tenant_id: UUID

    name: str = Field(description="Display name. Unique within tenant.")
    description: str | None = None

    type: PlanType
    price_cents: int = Field(ge=0, description="Cents, not dollars.")
    currency: str = Field(description="ISO 4217 — locked at creation time.")
    billing_period: BillingPeriod
    duration_days: int | None = Field(
        default=None,
        description=(
            "Only meaningful for one_time plans (e.g., 30-day trial pass). NULL for recurring."
        ),
    )

    is_active: bool = True
    custom_attrs: dict[str, Any] = Field(
        default_factory=dict,
        description="Ad-hoc per-tenant data. NOT for structured class rules — see entitlements.",
    )

    # entitlements are attached by the service/repo when fetched with details
    entitlements: list[PlanEntitlement] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    def can_be_subscribed_to(self) -> bool:
        """True if new subscriptions may reference this plan."""
        return self.is_active

    def is_unlimited_any_class(self) -> bool:
        """Zero entitlements = unlimited any class (simplest default)."""
        return len(self.entitlements) == 0
