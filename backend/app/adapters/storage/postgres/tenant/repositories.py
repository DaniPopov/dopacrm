"""Repository for the ``tenants`` table.

Translates between ``TenantORM`` (persistence) and ``Tenant`` (domain).
The Pydantic entity is the only thing that crosses the layer boundary —
callers never see the SQLAlchemy class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.adapters.storage.postgres.tenant.models import TenantORM
from app.domain.entities.tenant import Tenant

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: TenantORM) -> Tenant:
    """Map a SQLAlchemy row to the Pydantic domain entity."""
    return Tenant(
        id=orm.id,
        slug=orm.slug,
        name=orm.name,
        phone=orm.phone,
        is_active=orm.status,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class TenantRepository:
    """CRUD for tenants. Owns no transaction — pass in an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        slug: str,
        name: str,
        phone: str | None = None,
        is_active: bool = True,
    ) -> Tenant:
        """Insert a new tenant and return the domain entity."""
        orm = TenantORM(slug=slug, name=name, phone=phone, status=is_active)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, tenant_id: UUID) -> Tenant | None:
        """Look up by primary key. Returns None if not found."""
        result = await self._session.execute(select(TenantORM).where(TenantORM.id == tenant_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_slug(self, slug: str) -> Tenant | None:
        """Look up by unique slug. Returns None if not found."""
        result = await self._session.execute(select(TenantORM).where(TenantORM.slug == slug))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None
