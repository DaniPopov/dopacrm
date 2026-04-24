"""Repository for the ``class_coaches`` link table.

Three query shapes this repo serves:

1. CRUD + list-by-class / list-by-coach for the owner-facing UI.
2. **Attribution lookup** — given ``(class_id, entered_at::date)``,
   return the candidate rows whose weekdays match (empty = always
   matches). Used by the attendance attribution hook.
3. **Earnings window scan** — given a coach + date range, return the
   set of (class, rate-row) tuples so the service can compute per-link
   pay. The window-clipping math happens in the service.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.class_coach.models import ClassCoachORM
from app.adapters.storage.postgres.coach.models import CoachORM
from app.domain.entities.class_coach import ClassCoach, PayModel, weekday_code
from app.domain.entities.coach import CoachStatus
from app.domain.exceptions import ClassCoachConflictError

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: ClassCoachORM) -> ClassCoach:
    return ClassCoach(
        id=orm.id,
        tenant_id=orm.tenant_id,
        class_id=orm.class_id,
        coach_id=orm.coach_id,
        role=orm.role,
        is_primary=orm.is_primary,
        pay_model=PayModel(orm.pay_model),
        pay_amount_cents=orm.pay_amount_cents,
        weekdays=list(orm.weekdays or []),
        starts_on=orm.starts_on,
        ends_on=orm.ends_on,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class ClassCoachRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        class_id: UUID,
        coach_id: UUID,
        role: str,
        is_primary: bool,
        pay_model: PayModel,
        pay_amount_cents: int,
        weekdays: list[str],
        starts_on: date | None = None,
        ends_on: date | None = None,
    ) -> ClassCoach:
        orm = ClassCoachORM(
            tenant_id=tenant_id,
            class_id=class_id,
            coach_id=coach_id,
            role=role,
            is_primary=is_primary,
            pay_model=pay_model.value,
            pay_amount_cents=pay_amount_cents,
            weekdays=weekdays,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ClassCoachConflictError(
                f"Coach already has role {role!r} on class {class_id}"
            ) from exc
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, link_id: UUID) -> ClassCoach | None:
        result = await self._session.execute(
            select(ClassCoachORM).where(ClassCoachORM.id == link_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_class(
        self,
        tenant_id: UUID,
        class_id: UUID,
        *,
        only_current: bool = False,
    ) -> list[ClassCoach]:
        """All coaches attached to a class. ``only_current=True`` excludes
        rows whose ``ends_on`` has passed (useful on the class detail
        page; owner still sees ended rows when reviewing history)."""
        stmt = select(ClassCoachORM).where(
            ClassCoachORM.tenant_id == tenant_id,
            ClassCoachORM.class_id == class_id,
        )
        if only_current:
            today = date.today()
            stmt = stmt.where(
                or_(
                    ClassCoachORM.ends_on.is_(None),
                    ClassCoachORM.ends_on >= today,
                )
            )
        stmt = stmt.order_by(ClassCoachORM.is_primary.desc(), ClassCoachORM.role.asc())
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def list_for_coach(
        self,
        tenant_id: UUID,
        coach_id: UUID,
        *,
        only_current: bool = False,
    ) -> list[ClassCoach]:
        """All classes a coach is attached to."""
        stmt = select(ClassCoachORM).where(
            ClassCoachORM.tenant_id == tenant_id,
            ClassCoachORM.coach_id == coach_id,
        )
        if only_current:
            today = date.today()
            stmt = stmt.where(
                or_(
                    ClassCoachORM.ends_on.is_(None),
                    ClassCoachORM.ends_on >= today,
                )
            )
        stmt = stmt.order_by(ClassCoachORM.starts_on.desc())
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def update(self, link_id: UUID, **fields: Any) -> ClassCoach | None:
        """Bulk UPDATE to avoid sync-IO on ``onupdate``."""
        if "pay_model" in fields and isinstance(fields["pay_model"], PayModel):
            fields["pay_model"] = fields["pay_model"].value
        if not fields:
            return await self.find_by_id(link_id)
        try:
            await self._session.execute(
                update(ClassCoachORM)
                .where(ClassCoachORM.id == link_id)
                .values(**fields)
            )
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ClassCoachConflictError(str(exc.orig)) from exc
        return await self.find_by_id(link_id)

    async def delete(self, link_id: UUID) -> bool:
        """Hard delete — returns True if a row was removed."""
        from sqlalchemy import delete as sa_delete

        result = await self._session.execute(
            sa_delete(ClassCoachORM).where(ClassCoachORM.id == link_id)
        )
        await self._session.flush()
        return bool(result.rowcount)

    # ── Attribution lookup (used by AttendanceService.record_entry) ──

    async def find_attribution_candidates(
        self,
        tenant_id: UUID,
        class_id: UUID,
        entered_at_date: date,
    ) -> list[ClassCoach]:
        """Return candidate (class, coach) links for an attendance entry.

        Filters applied:
        - same tenant, same class
        - ``starts_on <= entered_at_date``
        - ``ends_on IS NULL OR ends_on >= entered_at_date``
        - weekday matches: ``weekdays = '{}'`` (all days) OR
          ``weekdays @> ARRAY[<code>]``
        - coach row status = 'active' (a frozen/cancelled coach is not
          attributed)

        Rows sorted by ``is_primary DESC, coach_id ASC`` — the first row
        is the service's pick when multiple candidates match.
        """
        code = weekday_code(entered_at_date)
        # Postgres array predicates:
        # - ``weekdays @> ARRAY[code]`` (``contains``) → weekday is listed
        # - ``cardinality(weekdays) = 0``              → "every day" catch-all
        stmt = (
            select(ClassCoachORM)
            .join(CoachORM, CoachORM.id == ClassCoachORM.coach_id)
            .where(
                ClassCoachORM.tenant_id == tenant_id,
                ClassCoachORM.class_id == class_id,
                ClassCoachORM.starts_on <= entered_at_date,
                or_(
                    ClassCoachORM.ends_on.is_(None),
                    ClassCoachORM.ends_on >= entered_at_date,
                ),
                CoachORM.status == CoachStatus.ACTIVE.value,
                or_(
                    func.cardinality(ClassCoachORM.weekdays) == 0,
                    ClassCoachORM.weekdays.contains([code]),
                ),
            )
            .order_by(ClassCoachORM.is_primary.desc(), ClassCoachORM.coach_id.asc())
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    # ── Earnings scan ────────────────────────────────────────────────

    async def list_active_links_for_coach_in_range(
        self,
        tenant_id: UUID,
        coach_id: UUID,
        from_: date,
        to: date,
    ) -> list[ClassCoach]:
        """Links that have ANY overlap with [from_, to]. The earnings
        service clips each to the query window before computing pay."""
        stmt = select(ClassCoachORM).where(
            ClassCoachORM.tenant_id == tenant_id,
            ClassCoachORM.coach_id == coach_id,
            ClassCoachORM.starts_on <= to,
            or_(
                ClassCoachORM.ends_on.is_(None),
                ClassCoachORM.ends_on >= from_,
            ),
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def list_tenant_links_with_coach_status(
        self,
        tenant_id: UUID,
        *,
        only_active_coaches: bool = True,
    ) -> list[tuple[ClassCoach, CoachStatus]]:
        """For the earnings summary endpoint (all coaches, one row each).
        Joined with the coach status so the service can skip cancelled."""
        stmt = (
            select(ClassCoachORM, CoachORM.status)
            .join(CoachORM, CoachORM.id == ClassCoachORM.coach_id)
            .where(ClassCoachORM.tenant_id == tenant_id)
        )
        if only_active_coaches:
            stmt = stmt.where(CoachORM.status == CoachStatus.ACTIVE.value)
        result = await self._session.execute(stmt)
        return [(_to_domain(row[0]), CoachStatus(row[1])) for row in result.all()]
