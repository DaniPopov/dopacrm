"""Repository for the ``members`` table.

Translates between ``MemberORM`` (persistence) and ``Member`` (domain).
All tenant-scoping is enforced at the SERVICE layer — this repo accepts
raw tenant_id parameters and trusts the service to pass the right one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.member.models import MemberORM
from app.domain.entities.member import Member, MemberStatus
from app.domain.exceptions import MemberAlreadyExistsError, MemberNotFoundError

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: MemberORM) -> Member:
    """Map a SQLAlchemy row to the Pydantic domain entity."""
    return Member(
        id=orm.id,
        tenant_id=orm.tenant_id,
        first_name=orm.first_name,
        last_name=orm.last_name,
        phone=orm.phone,
        email=orm.email,
        date_of_birth=orm.date_of_birth,
        gender=orm.gender,
        status=MemberStatus(orm.status),
        join_date=orm.join_date,
        frozen_at=orm.frozen_at,
        frozen_until=orm.frozen_until,
        cancelled_at=orm.cancelled_at,
        notes=orm.notes,
        custom_fields=orm.custom_fields or {},
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class MemberRepository:
    """CRUD for members. Owns no transaction — pass in an AsyncSession."""

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
        date_of_birth: date | None = None,
        gender: str | None = None,
        status: MemberStatus = MemberStatus.ACTIVE,
        join_date: date | None = None,
        notes: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Member:
        """Insert a new member.

        Raises:
            MemberAlreadyExistsError: If (tenant_id, phone) already exists.
        """
        orm = MemberORM(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            date_of_birth=date_of_birth,
            gender=gender,
            status=status.value,
            join_date=join_date,
            notes=notes,
            custom_fields=custom_fields or {},
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise MemberAlreadyExistsError(phone) from exc
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, member_id: UUID) -> Member | None:
        """Look up by primary key. Returns None if not found.

        Does NOT filter by tenant — that's the service's job.
        """
        result = await self._session.execute(select(MemberORM).where(MemberORM.id == member_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_tenant_and_phone(self, tenant_id: UUID, phone: str) -> Member | None:
        """Look up by the (tenant_id, phone) unique pair."""
        result = await self._session.execute(
            select(MemberORM).where(
                MemberORM.tenant_id == tenant_id,
                MemberORM.phone == phone,
            )
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        status: list[MemberStatus] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Member]:
        """List members scoped to one tenant, with optional filters.

        - ``status``: filter to specific lifecycle states (e.g. only active).
        - ``search``: case-insensitive match against first_name, last_name,
          phone, or email. Trimmed; empty string is ignored.
        """
        stmt = select(MemberORM).where(MemberORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(MemberORM.status.in_([s.value for s in status]))
        if search and search.strip():
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(MemberORM.first_name).like(like),
                    func.lower(MemberORM.last_name).like(like),
                    func.lower(MemberORM.phone).like(like),
                    func.lower(func.coalesce(MemberORM.email, "")).like(like),
                )
            )
        stmt = stmt.order_by(MemberORM.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars()]

    async def count_for_tenant(self, tenant_id: UUID, *, status: MemberStatus | None = None) -> int:
        """Count members for a tenant, optionally filtered by status.

        Used by the dashboard widgets and by limit checks on create.
        """
        stmt = select(func.count(MemberORM.id)).where(MemberORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(MemberORM.status == status.value)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, member_id: UUID, **fields: Any) -> Member:
        """Update specific fields on a member row. Returns the updated entity.

        Raises:
            MemberNotFoundError: If no member matches ``member_id``.
        """
        # status is a MemberStatus enum in the service — store .value
        if "status" in fields and isinstance(fields["status"], MemberStatus):
            fields["status"] = fields["status"].value

        await self._session.execute(
            update(MemberORM).where(MemberORM.id == member_id).values(**fields)
        )
        await self._session.flush()
        result = await self._session.execute(select(MemberORM).where(MemberORM.id == member_id))
        orm = result.scalar_one_or_none()
        if orm is None:
            raise MemberNotFoundError(str(member_id))
        await self._session.refresh(orm)
        return _to_domain(orm)
