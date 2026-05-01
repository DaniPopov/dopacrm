"""SQLAlchemy async engine, session factory, and DeclarativeBase.

The engine is created lazily on first call to ``get_engine()`` so that
importing this module never opens a connection (keeps tests / CI fast and
keeps Pydantic validation out of the import path).

Usage in a repository:

    async with async_session_factory() as session:
        await session.execute(...)
        await session.commit()
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for every ORM model."""


@lru_cache
def get_engine() -> AsyncEngine:
    """Return a cached AsyncEngine bound to DATABASE_URL.

    asyncpg ignores the ``postgresql://`` scheme and wants
    ``postgresql+asyncpg://`` — we rewrite the scheme automatically.
    """
    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


@lru_cache
def _session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


def async_session_factory() -> AsyncSession:
    """Return a fresh AsyncSession from the cached factory.

    Always use as an async context manager so the session is closed:

        async with async_session_factory() as session:
            ...
    """
    return _session_factory()()
