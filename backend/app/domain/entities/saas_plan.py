"""Pydantic domain entity for SaaS plans (DopaCRM pricing tiers)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class BillingPeriod(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SaasPlan(BaseModel):
    """A DopaCRM pricing tier that a tenant (gym) subscribes to.

    Distinct from the gym's own membership plans — those are what the gym
    sells to its members. A SaaS plan is what the gym pays DopaCRM.
    """

    id: UUID
    code: str = Field(description="Stable identifier — never shown to users")
    name: str = Field(description="Display name (e.g. 'DopaCRM Standard')")
    price_cents: int = Field(ge=0, description="Price in the smallest currency unit")
    currency: str = Field(default="ILS", description="ISO 4217")
    billing_period: BillingPeriod = BillingPeriod.MONTHLY
    max_members: int = Field(ge=0, description="Hard cap on gym members")
    max_staff_users: int | None = Field(
        default=None,
        description="Hard cap on staff users. None = unlimited.",
    )
    features: dict = Field(default_factory=dict, description="Feature flags this plan grants")
    is_public: bool = Field(default=True, description="Visible for self-serve signup")
    created_at: datetime
    updated_at: datetime
