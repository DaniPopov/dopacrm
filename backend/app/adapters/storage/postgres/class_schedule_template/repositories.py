"""Repository for ``class_schedule_templates``.

CRUD + tenant-scoped list. Tenant scoping is enforced at the service
layer; this repo trusts the caller to pass the right tenant_id.

Status transitions use bulk UPDATE (same sync-IO-avoidance pattern as
Coach / Subscription repos).
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from app.adapters.storage.postgres.class_schedule_template.models import (
    ClassScheduleTemplateORM,
)
from app.domain.entities.class_schedule_template import ClassScheduleTemplate

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: ClassScheduleTemplateORM) -> ClassScheduleTemplate:
    return ClassScheduleTemplate(
        id=orm.id,
        tenant_id=orm.tenant_id,
        class_id=orm.class_id,
        weekdays=list(orm.weekdays or []),
        start_time=orm.start_time,
        end_time=orm.end_time,
        head_coach_id=orm.head_coach_id,
        assistant_coach_id=orm.assistant_coach_id,
        starts_on=orm.starts_on,
        ends_on=orm.ends_on,
        is_active=orm.is_active,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class ClassScheduleTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        class_id: UUID,
        weekdays: list[str],
        start_time: time,
        end_time: time,
        head_coach_id: UUID,
        assistant_coach_id: UUID | None,
        starts_on: date | None = None,
        ends_on: date | None = None,
    ) -> ClassScheduleTemplate:
        orm = ClassScheduleTemplateORM(
            tenant_id=tenant_id,
            class_id=class_id,
            weekdays=weekdays,
            start_time=start_time,
            end_time=end_time,
            head_coach_id=head_coach_id,
            assistant_coach_id=assistant_coach_id,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, template_id: UUID) -> ClassScheduleTemplate | None:
        result = await self._session.execute(
            select(ClassScheduleTemplateORM).where(
                ClassScheduleTemplateORM.id == template_id
            )
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        class_id: UUID | None = None,
        only_active: bool = False,
    ) -> list[ClassScheduleTemplate]:
        stmt = select(ClassScheduleTemplateORM).where(
            ClassScheduleTemplateORM.tenant_id == tenant_id
        )
        if class_id is not None:
            stmt = stmt.where(ClassScheduleTemplateORM.class_id == class_id)
        if only_active:
            stmt = stmt.where(ClassScheduleTemplateORM.is_active.is_(True))
        stmt = stmt.order_by(ClassScheduleTemplateORM.starts_on.desc())
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def list_all_active(self) -> list[ClassScheduleTemplate]:
        """Platform-wide active templates — used by the beat job to
        extend horizons for every tenant."""
        result = await self._session.execute(
            select(ClassScheduleTemplateORM).where(
                ClassScheduleTemplateORM.is_active.is_(True)
            )
        )
        return [_to_domain(o) for o in result.scalars()]

    async def update(
        self, template_id: UUID, **fields: Any
    ) -> ClassScheduleTemplate | None:
        if not fields:
            return await self.find_by_id(template_id)
        await self._session.execute(
            update(ClassScheduleTemplateORM)
            .where(ClassScheduleTemplateORM.id == template_id)
            .values(**fields)
        )
        await self._session.flush()
        return await self.find_by_id(template_id)

    async def deactivate(self, template_id: UUID) -> ClassScheduleTemplate | None:
        """Soft-delete — set is_active=False. Future sessions get
        cancelled by the service; historical sessions stay."""
        await self._session.execute(
            update(ClassScheduleTemplateORM)
            .where(ClassScheduleTemplateORM.id == template_id)
            .values(is_active=False)
        )
        await self._session.flush()
        return await self.find_by_id(template_id)
