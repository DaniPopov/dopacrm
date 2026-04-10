"""Integration test fixtures — real Postgres, real SQL.

Uses the dev Postgres container (make up-dev). Each test gets a fresh
session. Tables are cleaned after each test via DELETE.

Reads NEON_DATABASE_URL directly from env so you don't need ALL env vars
(MongoDB, AWS, etc.) set just to run DB tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.storage.postgres import Base

_DEFAULT_DB_URL = "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm"


def _get_db_url() -> str:
    url = os.getenv("NEON_DATABASE_URL", _DEFAULT_DB_URL)
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    """Create an engine, yield a session, clean tables, dispose engine."""
    engine = create_async_engine(_get_db_url(), echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s

    # Clean all tables after each test (reverse order respects FKs)
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    await engine.dispose()
