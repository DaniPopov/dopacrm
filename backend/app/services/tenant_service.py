"""Tenant service — orchestrates tenant CRUD with business logic.

This is Layer 2 (Orchestration). It sits between the API routes (Layer 1)
and the repository (Layer 4). All business rules live here:
- Who can create/update/delete tenants (super_admin only)
- Auto-assign default SaaS plan at creation
- Trial setup (14 days by default)
- Status transition rules

Routes call this service. The service calls the repository.
Routes NEVER call the repository directly.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import (
    TenantAlreadyExistsError,
    TenantRepository,
)
from app.core.time import utcnow
from app.domain.entities.tenant import Tenant, TenantStatus
from app.domain.exceptions import (
    InsufficientPermissionsError,
    TenantNotFoundError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload


TRIAL_PERIOD = timedelta(days=14)


class TenantService:
    """Orchestrates tenant operations with permission checks and business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TenantRepository(session)
        self._plan_repo = SaasPlanRepository(session)

    # ── Commands ─────────────────────────────────────────────────────────────

    async def create_tenant(
        self,
        *,
        caller: TokenPayload,
        slug: str,
        name: str,
        phone: str | None = None,
        logo_url: str | None = None,
        email: str | None = None,
        website: str | None = None,
        address_street: str | None = None,
        address_city: str | None = None,
        address_country: str | None = "IL",
        address_postal_code: str | None = None,
        legal_name: str | None = None,
        tax_id: str | None = None,
        timezone: str = "Asia/Jerusalem",
        currency: str = "ILS",
        locale: str = "he-IL",
    ) -> Tenant:
        """Create a new gym tenant on a 14-day trial. Only super_admin can do this.

        Automatically:
        - Fetches the default SaaS plan and assigns it
        - Sets status = 'trial'
        - Sets trial_ends_at = now + 14 days
        """
        self._require_super_admin(caller)

        default_plan = await self._plan_repo.find_default()
        if default_plan is None:
            from app.domain.exceptions import AppError

            raise AppError(
                "No default SaaS plan found — seed data missing",
                "MISSING_DEFAULT_PLAN",
            )

        trial_ends_at = utcnow() + TRIAL_PERIOD

        try:
            tenant = await self._repo.create(
                slug=slug,
                name=name,
                saas_plan_id=default_plan.id,
                phone=phone,
                status=TenantStatus.TRIAL.value,
                logo_url=logo_url,
                email=email,
                website=website,
                address_street=address_street,
                address_city=address_city,
                address_country=address_country,
                address_postal_code=address_postal_code,
                legal_name=legal_name,
                tax_id=tax_id,
                timezone=timezone,
                currency=currency,
                locale=locale,
                trial_ends_at=trial_ends_at,
            )
        except TenantAlreadyExistsError as exc:
            from app.domain.exceptions import AppError

            raise AppError(str(exc), "TENANT_SLUG_TAKEN") from exc

        await self._session.commit()
        return tenant

    async def update_tenant(
        self,
        *,
        caller: TokenPayload,
        tenant_id: UUID,
        **fields,
    ) -> Tenant:
        """Partial update. super_admin can update any tenant."""
        self._require_super_admin(caller)
        await self._get_or_raise(tenant_id)
        updated = await self._repo.update(tenant_id, **fields)
        await self._session.commit()
        return updated

    async def suspend_tenant(
        self,
        *,
        caller: TokenPayload,
        tenant_id: UUID,
    ) -> Tenant:
        """Suspend a tenant — blocks all their users from accessing the platform."""
        self._require_super_admin(caller)
        await self._get_or_raise(tenant_id)
        updated = await self._repo.update(tenant_id, status=TenantStatus.SUSPENDED.value)
        await self._session.commit()
        return updated

    async def activate_tenant(
        self,
        *,
        caller: TokenPayload,
        tenant_id: UUID,
    ) -> Tenant:
        """Move a tenant to active status (out of trial/suspended/cancelled)."""
        self._require_super_admin(caller)
        await self._get_or_raise(tenant_id)
        updated = await self._repo.update(tenant_id, status=TenantStatus.ACTIVE.value)
        await self._session.commit()
        return updated

    async def cancel_tenant(
        self,
        *,
        caller: TokenPayload,
        tenant_id: UUID,
    ) -> Tenant:
        """Soft-delete a tenant (status=cancelled). Data is preserved."""
        self._require_super_admin(caller)
        await self._get_or_raise(tenant_id)
        updated = await self._repo.update(tenant_id, status=TenantStatus.CANCELLED.value)
        await self._session.commit()
        return updated

    # ── Queries ──────────────────────────────────────────────────────────────

    async def get_tenant(self, tenant_id: UUID) -> Tenant:
        """Get a single tenant by ID."""
        return await self._get_or_raise(tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Tenant:
        """Get a single tenant by slug."""
        tenant = await self._repo.find_by_slug(slug)
        if not tenant:
            raise TenantNotFoundError(slug)
        return tenant

    async def list_tenants(
        self,
        *,
        caller: TokenPayload,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tenant]:
        """List all tenants. super_admin only."""
        self._require_super_admin(caller)
        return await self._repo.list_all(limit=limit, offset=offset)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_or_raise(self, tenant_id: UUID) -> Tenant:
        """Fetch tenant or raise TenantNotFoundError."""
        tenant = await self._repo.find_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundError(str(tenant_id))
        return tenant

    @staticmethod
    def _require_super_admin(caller: TokenPayload) -> None:
        """Raise if the caller is not super_admin."""
        if caller.role != "super_admin":
            raise InsufficientPermissionsError()
