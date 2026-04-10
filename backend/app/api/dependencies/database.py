"""FastAPI dependency: async database session per request."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage.postgres.database import async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield an AsyncSession and close it when the request finishes."""
    async with async_session_factory() as session:
        yield session
