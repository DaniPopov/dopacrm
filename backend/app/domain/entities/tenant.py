"""Pydantic domain entity for tenants (gym accounts)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class TenantStatus(StrEnum):
    """Lifecycle status of a tenant."""

    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Tenant(BaseModel):
    """A registered gym on the platform — the top-level tenant.

    Stored in Postgres. The ``slug`` links to the corresponding
    tenant config document in MongoDB.
    """

    id: UUID
    slug: str
    name: str
    phone: str | None = None
    status: TenantStatus = TenantStatus.ACTIVE
    timezone: str = Field(default="Asia/Jerusalem", description="IANA timezone")
    currency: str = Field(default="ILS", description="ISO 4217 currency code")
    locale: str = Field(default="he-IL", description="BCP 47 locale")
    trial_ends_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    def is_active(self) -> bool:
        """Can this tenant's users access the platform?"""
        return self.status in (TenantStatus.TRIAL, TenantStatus.ACTIVE)
