"""Tenant service — orchestrates tenant CRUD with business logic.

This is Layer 2 (Orchestration). It sits between the API routes (Layer 1)
and the repository (Layer 4). All business rules live here:
- Who can create/update/delete tenants (super_admin only)
- Slug validation
- Status transition rules

Routes call this service. The service calls the repository.
Routes NEVER call the repository directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.adapters.storage.postgres.tenant.repositories import (
    TenantAlreadyExistsError,
    TenantRepository,
)
from app.core.security import TokenPayload
from app.domain.entities.tenant import Tenant, TenantStatus
from app.domain.exceptions import (
    InsufficientPermissionsError,
    TenantNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TenantService:
    """Orchestrates tenant operations with permission checks and business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TenantRepository(session)

    # ── Commands ─────────────────────────────────────────────────────────────

    async def create_tenant(
        self,
        *,
        caller: TokenPayload,
        slug: str,
        name: str,
        phone: str | None = None,
        timezone: str = "Asia/Jerusalem",
        currency: str = "ILS",
        locale: str = "he-IL",
    ) -> Tenant:
        """Create a new gym tenant. Only super_admin can do this."""
        self._require_super_admin(caller)

        try:
            tenant = await self._repo.create(
                slug=slug,
                name=name,
                phone=phone,
                status=TenantStatus.ACTIVE.value,
                timezone=timezone,
                currency=currency,
                locale=locale,
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

        # Make sure tenant exists
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
