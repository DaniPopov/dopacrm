"""Repository for the ``tenants`` table.

Translates between ``TenantORM`` (persistence) and ``Tenant`` (domain).
The Pydantic entity is the only thing that crosses the layer boundary —
callers never see the SQLAlchemy class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.tenant.models import TenantORM
from app.domain.entities.tenant import Tenant, TenantStatus
from app.domain.exceptions import TenantNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class TenantAlreadyExistsError(Exception):
    """Slug collision."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Tenant with slug '{slug}' already exists")
        self.slug = slug


def _to_domain(orm: TenantORM) -> Tenant:
    """Map a SQLAlchemy row to the Pydantic domain entity."""
    return Tenant(
        id=orm.id,
        slug=orm.slug,
        name=orm.name,
        phone=orm.phone,
        status=TenantStatus(orm.status),
        timezone=orm.timezone,
        currency=orm.currency,
        locale=orm.locale,
        trial_ends_at=orm.trial_ends_at,
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
        status: str = "active",
        timezone: str = "Asia/Jerusalem",
        currency: str = "ILS",
        locale: str = "he-IL",
    ) -> Tenant:
        """Insert a new tenant and return the domain entity."""
        orm = TenantORM(
            slug=slug,
            name=name,
            phone=phone,
            status=status,
            timezone=timezone,
            currency=currency,
            locale=locale,
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise TenantAlreadyExistsError(slug) from exc
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

    async def list_all(self, *, limit: int = 50, offset: int = 0) -> list[Tenant]:
        """Return all tenants. Paginated. For super_admin only."""
        result = await self._session.execute(
            select(TenantORM).order_by(TenantORM.created_at.desc()).limit(limit).offset(offset)
        )
        return [_to_domain(orm) for orm in result.scalars()]

    async def update(self, tenant_id: UUID, **fields) -> Tenant:
        """Update specific fields on a tenant row. Returns the updated entity."""
        await self._session.execute(
            update(TenantORM).where(TenantORM.id == tenant_id).values(**fields)
        )
        await self._session.flush()
        result = await self._session.execute(select(TenantORM).where(TenantORM.id == tenant_id))
        orm = result.scalar_one_or_none()
        if orm is None:
            raise TenantNotFoundError(str(tenant_id))
        await self._session.refresh(orm)
        return _to_domain(orm)
