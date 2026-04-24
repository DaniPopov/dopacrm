"""Repository for the ``coaches`` table.

Translates between ``CoachORM`` (persistence) and ``Coach`` (domain).
Tenant scoping is enforced at the service layer — this repo accepts
raw tenant_id parameters and trusts the service to pass the right one.

Status transitions (freeze / unfreeze / cancel) use bulk ``UPDATE``
statements rather than ORM attribute mutation — the ``onupdate=func.now()``
column otherwise expires after flush and triggers sync IO under
asyncpg (the subscriptions module hit this and documented it). Same
pattern applied preventively here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update

from app.adapters.storage.postgres.coach.models import CoachORM
from app.domain.entities.coach import Coach, CoachStatus

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: CoachORM) -> Coach:
    return Coach(
        id=orm.id,
        tenant_id=orm.tenant_id,
        user_id=orm.user_id,
        first_name=orm.first_name,
        last_name=orm.last_name,
        phone=orm.phone,
        email=orm.email,
        hired_at=orm.hired_at,
        status=CoachStatus(orm.status),
        frozen_at=orm.frozen_at,
        cancelled_at=orm.cancelled_at,
        custom_attrs=orm.custom_attrs or {},
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class CoachRepository:
    """CRUD + status helpers for the coaches table. Owns no transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        email: str | None = None,
        user_id: UUID | None = None,
        hired_at=None,
        custom_attrs: dict[str, Any] | None = None,
    ) -> Coach:
        orm = CoachORM(
            tenant_id=tenant_id,
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            hired_at=hired_at,
            custom_attrs=custom_attrs or {},
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, coach_id: UUID) -> Coach | None:
        """Lookup by PK. Tenant scoping is the service's job."""
        result = await self._session.execute(
            select(CoachORM).where(CoachORM.id == coach_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_user_id(self, user_id: UUID) -> Coach | None:
        """Used by the coach-portal login flow — given a user, is there
        a linked coach row?"""
        result = await self._session.execute(
            select(CoachORM).where(CoachORM.user_id == user_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        status: list[CoachStatus] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Coach]:
        """Owner-facing list. Search matches first/last name + phone + email."""
        stmt = select(CoachORM).where(CoachORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(CoachORM.status.in_([s.value for s in status]))
        if search and search.strip():
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(CoachORM.first_name).like(like),
                    func.lower(CoachORM.last_name).like(like),
                    func.lower(func.coalesce(CoachORM.phone, "")).like(like),
                    func.lower(func.coalesce(CoachORM.email, "")).like(like),
                )
            )
        stmt = (
            stmt.order_by(CoachORM.status.asc(), CoachORM.first_name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def count_for_tenant(
        self, tenant_id: UUID, *, status: CoachStatus | None = None
    ) -> int:
        stmt = select(func.count(CoachORM.id)).where(CoachORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(CoachORM.status == status.value)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, coach_id: UUID, **fields: Any) -> Coach | None:
        """Partial update — bulk UPDATE to avoid sync-IO on ``onupdate``.

        Returns the refreshed entity or None if no row matched.
        """
        if "status" in fields and isinstance(fields["status"], CoachStatus):
            fields["status"] = fields["status"].value
        if not fields:
            return await self.find_by_id(coach_id)
        await self._session.execute(
            update(CoachORM).where(CoachORM.id == coach_id).values(**fields)
        )
        await self._session.flush()
        return await self.find_by_id(coach_id)

    # ── State transitions (each is a bulk UPDATE) ────────────────────

    async def freeze(self, coach_id: UUID, *, frozen_at: datetime) -> Coach | None:
        await self._session.execute(
            update(CoachORM)
            .where(CoachORM.id == coach_id)
            .values(status=CoachStatus.FROZEN.value, frozen_at=frozen_at)
        )
        await self._session.flush()
        return await self.find_by_id(coach_id)

    async def unfreeze(self, coach_id: UUID) -> Coach | None:
        await self._session.execute(
            update(CoachORM)
            .where(CoachORM.id == coach_id)
            .values(status=CoachStatus.ACTIVE.value, frozen_at=None)
        )
        await self._session.flush()
        return await self.find_by_id(coach_id)

    async def cancel(self, coach_id: UUID, *, cancelled_at: datetime) -> Coach | None:
        await self._session.execute(
            update(CoachORM)
            .where(CoachORM.id == coach_id)
            .values(
                status=CoachStatus.CANCELLED.value,
                cancelled_at=cancelled_at,
                # Mirror member/sub pattern: cancelling from frozen clears frozen_at.
                frozen_at=None,
            )
        )
        await self._session.flush()
        return await self.find_by_id(coach_id)

    async def link_user(self, coach_id: UUID, user_id: UUID) -> Coach | None:
        """Idempotent — setting the same user_id twice is a no-op."""
        await self._session.execute(
            update(CoachORM).where(CoachORM.id == coach_id).values(user_id=user_id)
        )
        await self._session.flush()
        return await self.find_by_id(coach_id)
