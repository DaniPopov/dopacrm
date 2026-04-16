"""Gym class service — orchestrates class-catalog CRUD with business logic.

Layer 2. Sits between the API (Layer 1) and the repository (Layer 4).
Business rules live here:

- Tenant scoping: a user from gym A never sees/mutates gym B's classes.
- Permissions: owner+ can mutate, any tenant user can read (staff/sales
  need the catalog visible to sell passes or configure plans).
- Status transitions: deactivate / activate instead of delete. Existing
  references (plan_entitlements, class_passes) keep working.

super_admin is a special case: they can READ any tenant's classes but
cannot MUTATE (they're platform, not gym operators). Staff/sales can
read but not mutate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.domain.entities.user import Role
from app.domain.exceptions import (
    GymClassNotFoundError,
    InsufficientPermissionsError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload
    from app.domain.entities.gym_class import GymClass


class GymClassService:
    """Orchestrates class-catalog operations with permission + scoping checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = GymClassRepository(session)

    # ── Commands (owner+ only) ───────────────────────────────────────────────

    async def create(
        self,
        *,
        caller: TokenPayload,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> GymClass:
        """Create a class in the caller's tenant. Owner-only."""
        tenant_id = self._require_owner_in_tenant(caller)
        cls = await self._repo.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            color=color,
        )
        await self._session.commit()
        return cls

    async def update(
        self,
        *,
        caller: TokenPayload,
        class_id: UUID,
        **fields: Any,
    ) -> GymClass:
        """Partial update. Owner-only. Tenant-scoped."""
        self._require_owner(caller)
        await self._get_in_tenant(caller, class_id)
        updated = await self._repo.update(class_id, **fields)
        await self._session.commit()
        return updated

    async def deactivate(self, *, caller: TokenPayload, class_id: UUID) -> GymClass:
        """Soft-deactivate. Existing plan_entitlements keep working; new ones can't point here."""
        self._require_owner(caller)
        await self._get_in_tenant(caller, class_id)
        updated = await self._repo.update(class_id, is_active=False)
        await self._session.commit()
        return updated

    async def activate(self, *, caller: TokenPayload, class_id: UUID) -> GymClass:
        """Re-enable a deactivated class."""
        self._require_owner(caller)
        await self._get_in_tenant(caller, class_id)
        updated = await self._repo.update(class_id, is_active=True)
        await self._session.commit()
        return updated

    # ── Queries (any tenant user) ────────────────────────────────────────────

    async def get(self, *, caller: TokenPayload, class_id: UUID) -> GymClass:
        """Fetch one class. Tenant-scoped: returns 404 for other-tenant classes
        (no existence leak)."""
        return await self._get_in_tenant(caller, class_id)

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GymClass]:
        """List classes in the caller's tenant. Any tenant user can read —
        staff/sales need the catalog visible even if they can't mutate it."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_tenant(
            tenant_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )

    async def count_for_tenant(
        self, *, caller: TokenPayload, include_inactive: bool = False
    ) -> int:
        """Count classes in the caller's tenant (dashboard widget)."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.count_for_tenant(tenant_id, include_inactive=include_inactive)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_in_tenant(self, caller: TokenPayload, class_id: UUID) -> GymClass:
        """Fetch class + verify tenant match, or raise GymClassNotFoundError.

        super_admin bypasses tenant scoping — they can read across tenants
        for platform-level support. Tenant users see only their own gym's
        classes; a cross-tenant lookup returns 404, not 403, so the
        caller can't probe for existence.
        """
        cls = await self._repo.find_by_id(class_id)
        if cls is None:
            raise GymClassNotFoundError(str(class_id))
        if caller.role == Role.SUPER_ADMIN.value:
            return cls
        if caller.tenant_id is None or str(cls.tenant_id) != str(caller.tenant_id):
            raise GymClassNotFoundError(str(class_id))
        return cls

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> UUID:
        """Return the caller's tenant_id or raise. super_admin is rejected
        for class operations (they're platform-level, not gym-level)."""
        from uuid import UUID as _UUID

        if caller.role == Role.SUPER_ADMIN.value or caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_owner(caller: TokenPayload) -> None:
        """Mutations are owner-only (+ super_admin for platform support)."""
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()

    def _require_owner_in_tenant(self, caller: TokenPayload) -> UUID:
        """Combines owner check + tenant extraction for create()."""
        self._require_owner(caller)
        return self._require_tenant(caller)
