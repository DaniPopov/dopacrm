"""Repository for ``class_sessions``.

Four query shapes this repo serves:

1. CRUD for the service layer.
2. **Calendar range scan** — ``list_for_range(tenant, from_, to)`` —
   used by the week view on the Schedule page.
3. **Attribution lookup** — ``find_active_for_class(class_id, at, tol)`` —
   given a check-in time, find the scheduled session that covers it.
4. **Earnings scan** — ``count_for_coach(coach, class, [from, to])`` —
   replaces the v1 distinct-entry-days approximation.

Materialization uses ``insert ... on conflict do nothing`` so the
beat job can re-run without duplicating sessions (relies on the
partial UNIQUE index on ``(template_id, starts_at)``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.adapters.storage.postgres.class_session.models import ClassSessionORM
from app.domain.entities.class_session import ClassSession, SessionStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: ClassSessionORM) -> ClassSession:
    return ClassSession(
        id=orm.id,
        tenant_id=orm.tenant_id,
        class_id=orm.class_id,
        template_id=orm.template_id,
        starts_at=orm.starts_at,
        ends_at=orm.ends_at,
        head_coach_id=orm.head_coach_id,
        assistant_coach_id=orm.assistant_coach_id,
        status=SessionStatus(orm.status),
        is_customized=orm.is_customized,
        cancelled_at=orm.cancelled_at,
        cancelled_by=orm.cancelled_by,
        cancellation_reason=orm.cancellation_reason,
        notes=orm.notes,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class ClassSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ───────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: UUID,
        class_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        head_coach_id: UUID | None,
        assistant_coach_id: UUID | None = None,
        template_id: UUID | None = None,
        is_customized: bool = False,
        notes: str | None = None,
    ) -> ClassSession:
        """Plain insert for ad-hoc sessions. For template-backed
        materialization, use ``materialize_session`` — idempotent."""
        orm = ClassSessionORM(
            tenant_id=tenant_id,
            class_id=class_id,
            template_id=template_id,
            starts_at=starts_at,
            ends_at=ends_at,
            head_coach_id=head_coach_id,
            assistant_coach_id=assistant_coach_id,
            is_customized=is_customized,
            notes=notes,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def materialize_session(
        self,
        *,
        tenant_id: UUID,
        class_id: UUID,
        template_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        head_coach_id: UUID,
        assistant_coach_id: UUID | None,
    ) -> ClassSession | None:
        """Insert one materialized session. Idempotent via the partial
        UNIQUE index on ``(template_id, starts_at)``. Returns the
        inserted session, or None if a row already existed."""
        stmt = (
            pg_insert(ClassSessionORM)
            .values(
                tenant_id=tenant_id,
                class_id=class_id,
                template_id=template_id,
                starts_at=starts_at,
                ends_at=ends_at,
                head_coach_id=head_coach_id,
                assistant_coach_id=assistant_coach_id,
                status=SessionStatus.SCHEDULED.value,
                is_customized=False,
            )
            .on_conflict_do_nothing(
                index_elements=["template_id", "starts_at"],
                index_where=ClassSessionORM.template_id.is_not(None),
            )
            .returning(ClassSessionORM.id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None  # conflict — session already materialized
        new_id = row[0]
        await self._session.flush()
        return await self.find_by_id(new_id)

    # ── Read ─────────────────────────────────────────────────────────

    async def find_by_id(self, session_id: UUID) -> ClassSession | None:
        result = await self._session.execute(
            select(ClassSessionORM).where(ClassSessionORM.id == session_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_range(
        self,
        tenant_id: UUID,
        from_: datetime,
        to: datetime,
        *,
        class_id: UUID | None = None,
        coach_id: UUID | None = None,
        include_cancelled: bool = True,
    ) -> list[ClassSession]:
        """Calendar scan. ``from_`` inclusive, ``to`` exclusive."""
        stmt = select(ClassSessionORM).where(
            ClassSessionORM.tenant_id == tenant_id,
            ClassSessionORM.starts_at >= from_,
            ClassSessionORM.starts_at < to,
        )
        if class_id is not None:
            stmt = stmt.where(ClassSessionORM.class_id == class_id)
        if coach_id is not None:
            stmt = stmt.where(
                or_(
                    ClassSessionORM.head_coach_id == coach_id,
                    ClassSessionORM.assistant_coach_id == coach_id,
                )
            )
        if not include_cancelled:
            stmt = stmt.where(ClassSessionORM.status == SessionStatus.SCHEDULED.value)
        stmt = stmt.order_by(ClassSessionORM.starts_at)
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def find_active_for_class(
        self,
        tenant_id: UUID,
        class_id: UUID,
        at: datetime,
        tolerance: timedelta = timedelta(minutes=30),
    ) -> ClassSession | None:
        """Attribution lookup: pick the scheduled session that overlaps
        ``at ± tolerance``. If multiple overlap, pick the one whose
        ``starts_at`` is closest to ``at``."""
        stmt = (
            select(ClassSessionORM)
            .where(
                ClassSessionORM.tenant_id == tenant_id,
                ClassSessionORM.class_id == class_id,
                ClassSessionORM.status == SessionStatus.SCHEDULED.value,
                ClassSessionORM.starts_at <= at + tolerance,
                ClassSessionORM.ends_at >= at - tolerance,
            )
            # Closest starts_at first.
            .order_by(func.abs(func.extract("epoch", ClassSessionORM.starts_at - at)))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    # ── Update / mutate ───────────────────────────────────────────────

    async def update(self, session_id: UUID, **fields: Any) -> ClassSession | None:
        if "status" in fields and isinstance(fields["status"], SessionStatus):
            fields["status"] = fields["status"].value
        if not fields:
            return await self.find_by_id(session_id)
        await self._session.execute(
            update(ClassSessionORM).where(ClassSessionORM.id == session_id).values(**fields)
        )
        await self._session.flush()
        return await self.find_by_id(session_id)

    async def mark_customized(self, session_id: UUID) -> None:
        """Mark a session as manually edited. Called after cancel /
        swap / time-edit so re-materialization skips it."""
        await self._session.execute(
            update(ClassSessionORM)
            .where(ClassSessionORM.id == session_id)
            .values(is_customized=True)
        )
        await self._session.flush()

    # ── Template-driven queries ───────────────────────────────────────

    async def list_for_template_future(
        self, template_id: UUID, after: datetime
    ) -> list[ClassSession]:
        """Sessions spawned by this template starting after ``after``
        — used by re-materialization to update non-customized rows."""
        result = await self._session.execute(
            select(ClassSessionORM).where(
                ClassSessionORM.template_id == template_id,
                ClassSessionORM.starts_at >= after,
            )
        )
        return [_to_domain(o) for o in result.scalars()]

    async def latest_starts_at_for_template(self, template_id: UUID) -> datetime | None:
        """Horizon check for the beat job — what's the furthest-out
        materialized session for this template? None if nothing yet."""
        result = await self._session.execute(
            select(func.max(ClassSessionORM.starts_at)).where(
                ClassSessionORM.template_id == template_id
            )
        )
        return result.scalar_one_or_none()

    # ── Earnings + attribution count helpers ──────────────────────────

    async def count_scheduled_for_coach(
        self,
        *,
        tenant_id: UUID,
        coach_id: UUID,
        class_id: UUID,
        since: datetime,
        until: datetime,
    ) -> int:
        """Post-Schedule per_session pay math: count scheduled (not
        cancelled) sessions where this coach is the head coach."""
        result = await self._session.execute(
            select(func.count(ClassSessionORM.id)).where(
                ClassSessionORM.tenant_id == tenant_id,
                ClassSessionORM.head_coach_id == coach_id,
                ClassSessionORM.class_id == class_id,
                ClassSessionORM.status == SessionStatus.SCHEDULED.value,
                ClassSessionORM.starts_at >= since,
                ClassSessionORM.starts_at < until,
            )
        )
        return int(result.scalar_one())

    # ── Bulk actions ─────────────────────────────────────────────────

    async def list_in_range_for_class(
        self,
        *,
        tenant_id: UUID,
        class_id: UUID,
        from_date: datetime,
        to_date: datetime,
        scheduled_only: bool = True,
    ) -> list[ClassSession]:
        """Bulk range action — find every session to cancel / swap."""
        stmt = select(ClassSessionORM).where(
            ClassSessionORM.tenant_id == tenant_id,
            ClassSessionORM.class_id == class_id,
            ClassSessionORM.starts_at >= from_date,
            ClassSessionORM.starts_at < to_date,
        )
        if scheduled_only:
            stmt = stmt.where(ClassSessionORM.status == SessionStatus.SCHEDULED.value)
        stmt = stmt.order_by(ClassSessionORM.starts_at)
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]
