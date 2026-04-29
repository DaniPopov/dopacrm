"""Repository for the ``lead_activities`` table.

Append-only — only ``create`` and ``list_for_lead``. No update / delete
methods on purpose; the timeline is the audit trail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.adapters.storage.postgres.lead_activity.models import LeadActivityORM
from app.domain.entities.lead_activity import LeadActivity, LeadActivityType

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: LeadActivityORM) -> LeadActivity:
    return LeadActivity(
        id=orm.id,
        tenant_id=orm.tenant_id,
        lead_id=orm.lead_id,
        type=LeadActivityType(orm.type),
        note=orm.note,
        created_by=orm.created_by,
        created_at=orm.created_at,
    )


class LeadActivityRepository:
    """Append-only timeline writer + reader."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        lead_id: UUID,
        type: LeadActivityType,
        note: str,
        created_by: UUID | None = None,
    ) -> LeadActivity:
        orm = LeadActivityORM(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=type.value,
            note=note,
            created_by=created_by,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def list_for_lead(
        self, lead_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[LeadActivity]:
        stmt = (
            select(LeadActivityORM)
            .where(LeadActivityORM.lead_id == lead_id)
            .order_by(LeadActivityORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]
