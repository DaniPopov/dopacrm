"""Repository for the ``users`` table.

Translates between ``UserORM`` (persistence) and ``User`` (domain). The
password hash is never on the User entity — it's accepted as a parameter
on ``create()`` and only returned by the explicit ``find_with_credentials``
method, which the login flow uses to verify and then discards the hash.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.user.models import UserORM
from app.domain.entities.user import Role, User
from app.domain.exceptions import UserAlreadyExistsError

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: UserORM) -> User:
    """Map a SQLAlchemy row to the Pydantic domain entity."""
    return User(
        id=orm.id,
        tenant_id=orm.tenant_id,
        email=orm.email,
        role=Role(orm.role),
        is_active=orm.is_active,
        oauth_provider=orm.oauth_provider,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class UserRepository:
    """CRUD for users. Owns no transaction — pass in an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        role: Role,
        tenant_id: UUID | None = None,
        password_hash: str | None = None,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Insert a new user.

        Raises:
            UserAlreadyExistsError: If the (email, tenant_id) pair (or
                email + super_admin partial index) already exists.
        """
        orm = UserORM(
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
            role=role.value,
            is_active=is_active,
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise UserAlreadyExistsError(email) from exc
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, user_id: UUID) -> User | None:
        """Look up by primary key. Returns None if not found."""
        result = await self._session.execute(select(UserORM).where(UserORM.id == user_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_email(
        self,
        email: str,
        tenant_id: UUID | None = None,
    ) -> User | None:
        """Find a user by email within a company.

        Pass ``tenant_id=None`` to look up super_admin users (whose
        ``tenant_id`` is NULL). The query is automatically scoped via
        ``IS NULL`` for that case.
        """
        stmt = select(UserORM).where(UserORM.email == email)
        if tenant_id is None:
            stmt = stmt.where(UserORM.tenant_id.is_(None))
        else:
            stmt = stmt.where(UserORM.tenant_id == tenant_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_with_credentials(
        self,
        email: str,
        tenant_id: UUID | None = None,
    ) -> tuple[User, str | None] | None:
        """Like ``find_by_email`` but also returns the password hash.

        Used by the login flow only. The hash leaves the repository here
        but the caller (auth_service) verifies and discards it — never
        store it on the User entity, never serialize it, never log it.
        """
        stmt = select(UserORM).where(UserORM.email == email)
        if tenant_id is None:
            stmt = stmt.where(UserORM.tenant_id.is_(None))
        else:
            stmt = stmt.where(UserORM.tenant_id == tenant_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return _to_domain(orm), orm.password_hash

    async def find_any_by_email_with_credentials(
        self, email: str
    ) -> tuple[User, str | None] | None:
        """Find any user by email regardless of company — for login only.

        Returns the first matching user. This is safe because:
        1. The query is parameterized (no SQL injection)
        2. Password verification still happens after this call
        3. The JWT will contain the user's REAL tenant_id from the DB row

        If the same email exists in multiple companies (unlikely but
        allowed by schema), returns the first one found. The password
        check ensures only the real owner can log in.
        """
        result = await self._session.execute(select(UserORM).where(UserORM.email == email).limit(1))
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return _to_domain(orm), orm.password_hash

    async def list_all(self, *, limit: int = 50, offset: int = 0) -> list[User]:
        """Return all users (for super_admin). Paginated."""
        result = await self._session.execute(
            select(UserORM).order_by(UserORM.created_at.desc()).limit(limit).offset(offset)
        )
        return [_to_domain(orm) for orm in result.scalars()]

    async def list_by_tenant(
        self, tenant_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Return users in a specific company. Paginated."""
        result = await self._session.execute(
            select(UserORM)
            .where(UserORM.tenant_id == tenant_id)
            .order_by(UserORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_domain(orm) for orm in result.scalars()]

    async def update(self, user_id: UUID, **fields) -> User:
        """Update specific fields on a user row. Returns the updated entity.

        Raises:
            UserNotFoundError: If no user matches ``user_id``.
        """
        from app.domain.exceptions import UserNotFoundError

        # Map domain field names to ORM column names if they differ
        await self._session.execute(update(UserORM).where(UserORM.id == user_id).values(**fields))
        await self._session.flush()
        result = await self._session.execute(select(UserORM).where(UserORM.id == user_id))
        orm = result.scalar_one_or_none()
        if orm is None:
            raise UserNotFoundError(str(user_id))
        await self._session.refresh(orm)
        return _to_domain(orm)
