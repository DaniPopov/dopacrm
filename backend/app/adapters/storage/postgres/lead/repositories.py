"""Repository for the ``leads`` table.

Translates between ``LeadORM`` (persistence) and ``Lead`` (domain).
Tenant scoping is enforced at the service layer — this repo accepts
raw tenant_id parameters and trusts the service to pass the right one.

State transitions go through ``update`` (status + lost_reason +
converted_member_id flip together depending on the move). Bulk-style
``UPDATE`` rather than ORM attribute mutation, matching the Coach repo
pattern — ``onupdate=func.now()`` would otherwise expire after flush
and trigger sync IO under asyncpg.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update

from app.adapters.storage.postgres.lead.models import LeadORM
from app.domain.entities.lead import Lead, LeadSource, LeadStatus

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class LostReasonRow:
    """Aggregated lost-reason count for the autocomplete + future chart."""

    reason: str
    count: int


def _to_domain(orm: LeadORM) -> Lead:
    return Lead(
        id=orm.id,
        tenant_id=orm.tenant_id,
        first_name=orm.first_name,
        last_name=orm.last_name,
        email=orm.email,
        phone=orm.phone,
        source=LeadSource(orm.source),
        status=LeadStatus(orm.status),
        assigned_to=orm.assigned_to,
        notes=orm.notes,
        lost_reason=orm.lost_reason,
        converted_member_id=orm.converted_member_id,
        custom_fields=orm.custom_fields or {},
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class LeadRepository:
    """CRUD + status helpers + lost-reason aggregation. Owns no transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        first_name: str,
        last_name: str,
        phone: str,
        email: str | None = None,
        source: LeadSource = LeadSource.OTHER,
        assigned_to: UUID | None = None,
        notes: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Lead:
        orm = LeadORM(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            source=source.value,
            assigned_to=assigned_to,
            notes=notes,
            custom_fields=custom_fields or {},
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, lead_id: UUID) -> Lead | None:
        result = await self._session.execute(select(LeadORM).where(LeadORM.id == lead_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        status: list[LeadStatus] | None = None,
        source: list[LeadSource] | None = None,
        assigned_to: UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        stmt = select(LeadORM).where(LeadORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(LeadORM.status.in_([s.value for s in status]))
        if source:
            stmt = stmt.where(LeadORM.source.in_([s.value for s in source]))
        if assigned_to is not None:
            stmt = stmt.where(LeadORM.assigned_to == assigned_to)
        if search and search.strip():
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(LeadORM.first_name).like(like),
                    func.lower(LeadORM.last_name).like(like),
                    func.lower(LeadORM.phone).like(like),
                    func.lower(func.coalesce(LeadORM.email, "")).like(like),
                )
            )
        stmt = stmt.order_by(LeadORM.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def count_by_status(self, tenant_id: UUID) -> dict[LeadStatus, int]:
        """Return a count of leads per status. Backs the Kanban column
        headers and the dashboard 'leads in pipeline' widget. Statuses
        with zero rows are filled in by the caller."""
        stmt = (
            select(LeadORM.status, func.count(LeadORM.id))
            .where(LeadORM.tenant_id == tenant_id)
            .group_by(LeadORM.status)
        )
        result = await self._session.execute(stmt)
        return {LeadStatus(row[0]): int(row[1]) for row in result.all()}

    async def count_converted_since(self, tenant_id: UUID, *, since: datetime) -> int:
        """Count leads converted in the window (used for conversion-rate widget)."""
        stmt = select(func.count(LeadORM.id)).where(
            LeadORM.tenant_id == tenant_id,
            LeadORM.status == LeadStatus.CONVERTED.value,
            LeadORM.updated_at >= since,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_created_since(self, tenant_id: UUID, *, since: datetime) -> int:
        """Count leads created in the window (the conversion-rate denominator)."""
        stmt = select(func.count(LeadORM.id)).where(
            LeadORM.tenant_id == tenant_id,
            LeadORM.created_at >= since,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, lead_id: UUID, **fields: Any) -> Lead | None:
        """Partial update — bulk UPDATE to avoid sync-IO on ``onupdate``.

        The status / source / assigned_to enums are coerced to their
        ``.value`` form here so callers can pass either an enum member
        or a string.
        """
        if "status" in fields and isinstance(fields["status"], LeadStatus):
            fields["status"] = fields["status"].value
        if "source" in fields and isinstance(fields["source"], LeadSource):
            fields["source"] = fields["source"].value
        if not fields:
            return await self.find_by_id(lead_id)
        await self._session.execute(update(LeadORM).where(LeadORM.id == lead_id).values(**fields))
        await self._session.flush()
        return await self.find_by_id(lead_id)

    async def top_lost_reasons(
        self, tenant_id: UUID, *, since: datetime, limit: int = 10
    ) -> list[LostReasonRow]:
        """Aggregate lost reasons (case-insensitive collapse) for the
        autocomplete dropdown. Empty / NULL reasons excluded.
        """
        # Lower-case + trim, group, count, top-N.
        reason_expr = func.lower(func.trim(LeadORM.lost_reason))
        stmt = (
            select(reason_expr.label("reason"), func.count(LeadORM.id).label("count"))
            .where(
                LeadORM.tenant_id == tenant_id,
                LeadORM.status == LeadStatus.LOST.value,
                LeadORM.lost_reason.is_not(None),
                func.length(func.trim(LeadORM.lost_reason)) > 0,
                LeadORM.updated_at >= since,
            )
            .group_by(reason_expr)
            .order_by(func.count(LeadORM.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [LostReasonRow(reason=row[0], count=int(row[1])) for row in result.all()]
