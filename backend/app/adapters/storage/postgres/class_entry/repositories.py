"""Repository for ``class_entries``.

Two responsibilities:

1. CRUD-ish operations for the API layer (record an entry, soft-delete
   via undo, list by tenant/member, find by id).
2. The **quota-count query** used by the service's quota-check logic.
   This is the hot path — one query per member pick on the check-in
   page. It hits the partial index on ``(member_id, class_id, entered_at)
   WHERE undone_at IS NULL`` so it stays cheap even with millions of
   historical entries.

Tenant scoping is the SERVICE's responsibility; this repo trusts the
caller to pass the right tenant_id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, desc, func, select, update

from app.adapters.storage.postgres.class_entry.models import ClassEntryORM
from app.domain.entities.class_entry import ClassEntry, OverrideKind
from app.domain.exceptions import ClassEntryNotFoundError

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: ClassEntryORM) -> ClassEntry:
    return ClassEntry(
        id=orm.id,
        tenant_id=orm.tenant_id,
        member_id=orm.member_id,
        subscription_id=orm.subscription_id,
        class_id=orm.class_id,
        entered_at=orm.entered_at,
        entered_by=orm.entered_by,
        undone_at=orm.undone_at,
        undone_by=orm.undone_by,
        undone_reason=orm.undone_reason,
        override=orm.override,
        override_kind=OverrideKind(orm.override_kind) if orm.override_kind else None,
        override_reason=orm.override_reason,
    )


class ClassEntryRepository:
    """CRUD + quota-count for class entries. No transactions owned."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ──────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: UUID,
        member_id: UUID,
        subscription_id: UUID,
        class_id: UUID,
        entered_by: UUID | None,
        override: bool = False,
        override_kind: OverrideKind | None = None,
        override_reason: str | None = None,
    ) -> ClassEntry:
        """Insert a new entry. ``entered_at`` is set by the DB (NOW())."""
        orm = ClassEntryORM(
            tenant_id=tenant_id,
            member_id=member_id,
            subscription_id=subscription_id,
            class_id=class_id,
            entered_by=entered_by,
            override=override,
            override_kind=override_kind.value if override_kind else None,
            override_reason=override_reason,
        )
        self._session.add(orm)
        await self._session.flush()
        new_id = orm.id
        # Re-fetch to pick up server-populated entered_at (server_default=NOW())
        refreshed = await self.find_by_id(new_id)
        assert refreshed is not None
        return refreshed

    # ── Read ────────────────────────────────────────────────────────────

    async def find_by_id(self, entry_id: UUID) -> ClassEntry | None:
        result = await self._session.execute(
            select(ClassEntryORM).where(ClassEntryORM.id == entry_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        member_id: UUID | None = None,
        class_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_undone: bool = False,
        undone_only: bool = False,
        override_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClassEntry]:
        """List entries. Newest first. Multiple optional filters.

        ``include_undone`` - default False (effective rows only).
        ``undone_only`` - inverse: only rows that have been undone.
        ``override_only`` - only rows with override=true (owner audit).
        """
        stmt = select(ClassEntryORM).where(ClassEntryORM.tenant_id == tenant_id)
        if member_id is not None:
            stmt = stmt.where(ClassEntryORM.member_id == member_id)
        if class_id is not None:
            stmt = stmt.where(ClassEntryORM.class_id == class_id)
        if date_from is not None:
            stmt = stmt.where(ClassEntryORM.entered_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(ClassEntryORM.entered_at < date_to)
        if undone_only:
            stmt = stmt.where(ClassEntryORM.undone_at.is_not(None))
        elif not include_undone:
            stmt = stmt.where(ClassEntryORM.undone_at.is_(None))
        if override_only:
            stmt = stmt.where(ClassEntryORM.override.is_(True))
        stmt = stmt.order_by(desc(ClassEntryORM.entered_at)).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars()]

    async def list_for_member(
        self, tenant_id: UUID, member_id: UUID, *, limit: int = 50
    ) -> list[ClassEntry]:
        """Full history for one member, newest first. Includes undone
        entries so the member detail timeline can show them with an
        "undone" marker."""
        result = await self._session.execute(
            select(ClassEntryORM)
            .where(
                ClassEntryORM.tenant_id == tenant_id,
                ClassEntryORM.member_id == member_id,
            )
            .order_by(desc(ClassEntryORM.entered_at))
            .limit(limit)
        )
        return [_to_domain(orm) for orm in result.scalars()]

    # ── Quota-count (the hot path) ─────────────────────────────────────

    async def count_effective_entries(
        self,
        *,
        member_id: UUID,
        class_id: UUID | None,
        since: datetime,
    ) -> int:
        """Count effective (non-undone) entries for this member in a
        time window.

        ``class_id=None`` means "count across all classes" — used for
        any-class entitlements (the wildcard form). ``class_id`` set
        means "count only entries for this specific class".

        Hits the partial index ``ix_entries_effective`` directly.
        """
        stmt = select(func.count(ClassEntryORM.id)).where(
            ClassEntryORM.member_id == member_id,
            ClassEntryORM.undone_at.is_(None),
            ClassEntryORM.entered_at >= since,
        )
        if class_id is not None:
            stmt = stmt.where(ClassEntryORM.class_id == class_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    # ── Undo (soft-delete) ─────────────────────────────────────────────

    async def undo(
        self,
        entry_id: UUID,
        *,
        undone_at: datetime,
        undone_by: UUID | None,
        undone_reason: str | None,
    ) -> ClassEntry:
        """Mark an entry as undone. Service checks the 24h window first."""
        existing = await self.find_by_id(entry_id)
        if existing is None:
            raise ClassEntryNotFoundError(str(entry_id))

        await self._session.execute(
            update(ClassEntryORM)
            .where(ClassEntryORM.id == entry_id)
            .values(
                undone_at=undone_at,
                undone_by=undone_by,
                undone_reason=undone_reason,
            )
        )
        await self._session.flush()
        refreshed = await self.find_by_id(entry_id)
        assert refreshed is not None
        return refreshed

    # ── Aggregates for dashboards ─────────────────────────────────────

    async def count_for_day(self, tenant_id: UUID, day: datetime) -> int:
        """Effective check-ins for a given tenant + UTC day.

        ``day`` is the start of the day (00:00 UTC). Caller shapes the
        timezone conversion. Used by the "check-ins today" dashboard
        widget.
        """
        next_day = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        result = await self._session.execute(
            select(func.count(ClassEntryORM.id)).where(
                and_(
                    ClassEntryORM.tenant_id == tenant_id,
                    ClassEntryORM.undone_at.is_(None),
                    ClassEntryORM.entered_at >= day,
                    ClassEntryORM.entered_at <= next_day,
                )
            )
        )
        return int(result.scalar_one())
