"""Repository for the ``classes`` table.

Translates between ``GymClassORM`` (persistence) and ``GymClass``
(domain). Tenant-scoping is the SERVICE's job — this repo accepts
raw tenant_id parameters and trusts the service to pass the right one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.gym_class.models import GymClassORM
from app.domain.entities.gym_class import GymClass
from app.domain.exceptions import GymClassAlreadyExistsError, GymClassNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: GymClassORM) -> GymClass:
    """Map a SQLAlchemy row to the Pydantic domain entity."""
    return GymClass(
        id=orm.id,
        tenant_id=orm.tenant_id,
        name=orm.name,
        description=orm.description,
        color=orm.color,
        is_active=orm.is_active,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class GymClassRepository:
    """CRUD for gym classes. Owns no transaction — pass in an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        name: str,
        description: str | None = None,
        color: str | None = None,
        is_active: bool = True,
    ) -> GymClass:
        """Insert a new class.

        Raises:
            GymClassAlreadyExistsError: If (tenant_id, name) already exists.
        """
        orm = GymClassORM(
            tenant_id=tenant_id,
            name=name,
            description=description,
            color=color,
            is_active=is_active,
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise GymClassAlreadyExistsError(name) from exc
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, class_id: UUID) -> GymClass | None:
        """Look up by primary key. Returns None if not found.

        Does NOT filter by tenant — that's the service's job, so a
        super_admin impersonation flow (future) can still read across.
        """
        result = await self._session.execute(select(GymClassORM).where(GymClassORM.id == class_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_tenant_and_name(self, tenant_id: UUID, name: str) -> GymClass | None:
        """Look up by the (tenant_id, name) unique pair."""
        result = await self._session.execute(
            select(GymClassORM).where(
                GymClassORM.tenant_id == tenant_id,
                GymClassORM.name == name,
            )
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GymClass]:
        """List classes in one tenant. Defaults to active only — owner
        can pass include_inactive=True to see the full catalog."""
        stmt = select(GymClassORM).where(GymClassORM.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(GymClassORM.is_active.is_(True))
        stmt = stmt.order_by(GymClassORM.name.asc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars()]

    async def count_for_tenant(self, tenant_id: UUID, *, include_inactive: bool = False) -> int:
        """Count classes for a tenant. Used by dashboard + limit checks."""
        stmt = select(func.count(GymClassORM.id)).where(GymClassORM.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(GymClassORM.is_active.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, class_id: UUID, **fields: Any) -> GymClass:
        """Update specific fields on a class row. Returns the updated entity.

        Raises:
            GymClassNotFoundError: If no class matches ``class_id``.
            GymClassAlreadyExistsError: If renaming would collide with
                another class in the same tenant.
        """
        try:
            await self._session.execute(
                update(GymClassORM).where(GymClassORM.id == class_id).values(**fields)
            )
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise GymClassAlreadyExistsError(str(fields.get("name", ""))) from exc

        result = await self._session.execute(select(GymClassORM).where(GymClassORM.id == class_id))
        orm = result.scalar_one_or_none()
        if orm is None:
            raise GymClassNotFoundError(str(class_id))
        await self._session.refresh(orm)
        return _to_domain(orm)
