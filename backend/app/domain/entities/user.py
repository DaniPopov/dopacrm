"""Pydantic domain entity for dashboard users.

Separate from the SQLAlchemy ORM in ``adapters/storage/postgres/user/`` —
the ORM is the persistence shape, this is the domain shape that crosses
layer boundaries. Repositories translate between the two at the boundary.

The User entity intentionally does **not** carry the password hash —
credentials are a separate concern, passed explicitly to mutation methods
on the repository (``create(..., password_hash=...)``). Read paths never
need to see the hash.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Role(StrEnum):
    """User role hierarchy.

    ``super_admin`` is platform-level (``tenant_id = None``).
    Every other role belongs to exactly one company (gym tenant).

    - owner: full tenant access, billing, configuration
    - staff: day-to-day operations (check-in, payments, members)
    - sales: lead pipeline, trials, conversions
    - coach: trainer. Tied 1:1 to a ``coaches`` row via
      ``coaches.user_id``. Baseline view is read-only + narrow
      (their own classes, attendance, earnings). See
      ``docs/features/coaches.md`` §8.
    """

    SUPER_ADMIN = "super_admin"
    OWNER = "owner"
    STAFF = "staff"
    SALES = "sales"
    COACH = "coach"


class User(BaseModel):
    """A dashboard user — owner, staff, sales, or platform super_admin."""

    id: UUID
    tenant_id: UUID | None = Field(
        default=None,
        description="None for super_admin; UUID for company-scoped roles.",
    )
    email: str
    role: Role
    is_active: bool = True

    # Personal info — nullable for historical rows + OAuth flows
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None

    oauth_provider: str | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        """Best-effort display name. Falls back to email if no names set."""
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) if parts else self.email

    def is_super_admin(self) -> bool:
        """Pure logic — true for platform-level users (no company)."""
        return self.role == Role.SUPER_ADMIN

    def can_manage_tenant(self, tenant_id: UUID) -> bool:
        """Pure logic — does this user have management power over the given tenant?"""
        if self.is_super_admin():
            return True
        return self.tenant_id == tenant_id and self.role in (Role.OWNER, Role.STAFF)
