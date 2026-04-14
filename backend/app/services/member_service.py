"""Member service — orchestrates member CRUD with business logic.

Layer 2. Sits between the API (Layer 1) and the repository (Layer 4).
All business rules live here:
- Tenant scoping — a user from gym A never sees gym B's members, even
  with a forged UUID.
- Status transitions — enforced via can_freeze/can_unfreeze/can_cancel
  on the entity.
- Permission checks — cancel is owner+ only; everything else is any
  authenticated tenant user. super_admin doesn't manage members (that's
  the gym's concern) but we don't block them — they see all tenants.

Routes call this service. Routes NEVER call the repository directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.domain.entities.member import Member, MemberStatus
from app.domain.entities.user import Role
from app.domain.exceptions import (
    InsufficientPermissionsError,
    InvalidMemberStatusTransitionError,
    MemberNotFoundError,
)

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload


class MemberService:
    """Orchestrates member operations with permission checks and business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MemberRepository(session)

    # ── Commands ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        caller: TokenPayload,
        first_name: str,
        last_name: str,
        phone: str,
        email: str | None = None,
        date_of_birth: date | None = None,
        gender: str | None = None,
        join_date: date | None = None,
        notes: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Member:
        """Create a new member in the caller's tenant.

        super_admin cannot create a member — they're platform, not gym.
        """
        tenant_id = self._require_tenant(caller)
        member = await self._repo.create(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            date_of_birth=date_of_birth,
            gender=gender,
            join_date=join_date,
            notes=notes,
            custom_fields=custom_fields,
        )
        await self._session.commit()
        return member

    async def update(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
        **fields: Any,
    ) -> Member:
        """Partial update. Tenant-scoped."""
        await self._get_in_tenant(caller, member_id)
        updated = await self._repo.update(member_id, **fields)
        await self._session.commit()
        return updated

    async def freeze(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
        until: date | None = None,
    ) -> Member:
        """Freeze a member. Only active members can be frozen."""
        from app.core.time import utcnow

        member = await self._get_in_tenant(caller, member_id)
        if not member.can_freeze():
            raise InvalidMemberStatusTransitionError(member.status.value, "freeze")
        updated = await self._repo.update(
            member_id,
            status=MemberStatus.FROZEN,
            frozen_at=utcnow().date(),
            frozen_until=until,
        )
        await self._session.commit()
        return updated

    async def unfreeze(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
    ) -> Member:
        """Unfreeze a member — status back to active."""
        member = await self._get_in_tenant(caller, member_id)
        if not member.can_unfreeze():
            raise InvalidMemberStatusTransitionError(member.status.value, "unfreeze")
        updated = await self._repo.update(
            member_id,
            status=MemberStatus.ACTIVE,
            frozen_at=None,
            frozen_until=None,
        )
        await self._session.commit()
        return updated

    async def cancel(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
    ) -> Member:
        """Cancel a member — terminal state. owner+ only."""
        from app.core.time import utcnow

        self._require_owner_or_super_admin(caller)
        member = await self._get_in_tenant(caller, member_id)
        if not member.can_cancel():
            raise InvalidMemberStatusTransitionError(member.status.value, "cancel")
        updated = await self._repo.update(
            member_id,
            status=MemberStatus.CANCELLED,
            cancelled_at=utcnow().date(),
        )
        await self._session.commit()
        return updated

    # ── Queries ──────────────────────────────────────────────────────────────

    async def get(self, *, caller: TokenPayload, member_id: UUID) -> Member:
        """Fetch one member. Tenant-scoped: returns 404 even for members
        in other tenants (don't leak existence).
        """
        return await self._get_in_tenant(caller, member_id)

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        status: list[MemberStatus] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Member]:
        """List members in the caller's tenant."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_tenant(
            tenant_id, status=status, search=search, limit=limit, offset=offset
        )

    async def count_for_tenant(
        self, *, caller: TokenPayload, status: MemberStatus | None = None
    ) -> int:
        """Count members in the caller's tenant, optionally by status.

        Used by dashboard widgets. super_admin gets 0 (no tenant).
        """
        tenant_id = self._require_tenant(caller)
        return await self._repo.count_for_tenant(tenant_id, status=status)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_in_tenant(self, caller: TokenPayload, member_id: UUID) -> Member:
        """Fetch member, verify tenant match, or raise MemberNotFoundError.

        super_admin bypasses tenant scoping — they can read/update anywhere.
        """
        member = await self._repo.find_by_id(member_id)
        if member is None:
            raise MemberNotFoundError(str(member_id))
        if caller.role == Role.SUPER_ADMIN.value:
            return member
        # Non-super_admin: member must belong to the caller's tenant.
        # We raise NotFound (not Forbidden) to avoid leaking existence.
        if caller.tenant_id is None or str(member.tenant_id) != str(caller.tenant_id):
            raise MemberNotFoundError(str(member_id))
        return member

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> UUID:
        """Return the caller's tenant_id or raise. super_admin is rejected
        for member operations (they're platform, not gym).
        """
        from uuid import UUID as _UUID

        if caller.role == Role.SUPER_ADMIN.value or caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_owner_or_super_admin(caller: TokenPayload) -> None:
        """Cancel is owner+ only."""
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()
