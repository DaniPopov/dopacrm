"""User service — orchestrates user CRUD with business logic.

This is Layer 2 (Orchestration). It sits between the API routes (Layer 1)
and the repository (Layer 4). All business rules live here:
- Who can create users (super_admin only)
- Who can see which users (tenant scoping)
- Validation (tenant_id required for non-super_admin roles)
- Password hashing before storage

Routes call this service. The service calls the repository.
Routes NEVER call the repository directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.security import TokenPayload, hash_password
from app.domain.entities.user import Role, User
from app.domain.exceptions import (
    InsufficientPermissionsError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UserService:
    """Orchestrates user operations with permission checks and business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    async def create_user(
        self,
        *,
        caller: TokenPayload,
        email: str,
        role: Role,
        tenant_id: UUID | None = None,
        password: str | None = None,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
    ) -> User:
        """Create a new user. Only super_admin can create users."""
        if caller.role != Role.SUPER_ADMIN.value:
            raise InsufficientPermissionsError()

        if role != Role.SUPER_ADMIN and tenant_id is None:
            msg = "tenant_id is required for non-super_admin roles"
            raise ValueError(msg)

        pwd_hash = None
        if password:
            pwd_hash = hash_password(password)
        elif not oauth_provider:
            msg = "Either password or oauth_provider must be provided"
            raise ValueError(msg)

        user = await self._repo.create(
            email=email,
            role=role,
            tenant_id=tenant_id,
            password_hash=pwd_hash,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
        )
        await self._session.commit()
        return user

    async def get_user(self, user_id: UUID) -> User:
        """Get a single user by ID."""
        user = await self._repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))
        return user

    async def list_users(
        self,
        caller: TokenPayload,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        """List users scoped by the caller's role.

        - super_admin: sees all users across all companies
        - admin/manager/worker: sees only users in their tenant

        Defense-in-depth: non-super_admin with tenant_id=None is rejected
        (should never happen if JWT is valid, but protects against data
        integrity bugs or token manipulation).
        """
        if caller.role == Role.SUPER_ADMIN.value:
            return await self._repo.list_all(limit=limit, offset=offset)
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return await self._repo.list_by_tenant(UUID(caller.tenant_id), limit=limit, offset=offset)

    async def update_user(
        self,
        user_id: UUID,
        **fields,
    ) -> User:
        """Partial update — only provided fields are changed."""
        await self.get_user(user_id)  # raises UserNotFoundError if missing
        updated = await self._repo.update(user_id, **fields)
        await self._session.commit()
        return updated

    async def soft_delete_user(self, user_id: UUID) -> None:
        """Soft-delete — sets is_active=False. No row is removed."""
        await self.get_user(user_id)  # raises UserNotFoundError if missing
        await self._repo.update(user_id, is_active=False)
        await self._session.commit()
