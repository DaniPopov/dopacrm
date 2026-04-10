"""Repository for the ``refresh_tokens`` table.

The raw token never lives on the entity. Callers pass a hashed token to
``create``, and look up by ``(token_hash, user_id)`` via ``find_by_hash``.
The login / refresh flow hashes the bearer token before calling either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.adapters.storage.postgres.refresh_token.models import RefreshTokenORM
from app.domain.entities.refresh_token import RefreshToken

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: RefreshTokenORM) -> RefreshToken:
    """Map a SQLAlchemy row to the Pydantic domain entity (no token_hash)."""
    return RefreshToken(
        id=orm.id,
        user_id=orm.user_id,
        expires_at=orm.expires_at,
        is_revoked=orm.revoked,
        created_at=orm.created_at,
    )


class RefreshTokenRepository:
    """CRUD for refresh tokens. Owns no transaction — pass in an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Insert a new refresh token row.

        ``token_hash`` is the only credential — never store the raw token.
        Hash before calling.
        """
        orm = RefreshTokenORM(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_hash(
        self,
        token_hash: str,
        user_id: UUID,
    ) -> RefreshToken | None:
        """Look up an active refresh token by hash + user.

        Returns None if no matching row OR if the row is revoked. Use
        ``is_expired`` on the returned entity to check the time window.
        """
        result = await self._session.execute(
            select(RefreshTokenORM).where(
                RefreshTokenORM.token_hash == token_hash,
                RefreshTokenORM.user_id == user_id,
                RefreshTokenORM.revoked.is_(False),
            )
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def revoke(self, token_id: UUID) -> None:
        """Mark a single token as revoked (logout from one device)."""
        await self._session.execute(
            update(RefreshTokenORM).where(RefreshTokenORM.id == token_id).values(revoked=True)
        )

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Revoke every active token for a user (force logout everywhere)."""
        await self._session.execute(
            update(RefreshTokenORM)
            .where(
                RefreshTokenORM.user_id == user_id,
                RefreshTokenORM.revoked.is_(False),
            )
            .values(revoked=True)
        )
