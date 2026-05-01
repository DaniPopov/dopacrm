"""Alembic environment.

Wired to the project's Settings — pulls the database URL from
``DATABASE_DIRECT_URL`` (or falls back to ``DATABASE_URL`` if direct isn't
set, which is the case for local Postgres where pooled and direct are
identical).

Imports ``app.adapters.storage.postgres`` to register every ORM class
with ``Base.metadata`` so autogenerate can see all tables.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.adapters.storage.postgres import Base  # registers all ORM models
from app.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Set the database URL from app settings (overrides alembic.ini).
_settings = get_settings()
_db_url = _settings.DATABASE_DIRECT_URL or _settings.DATABASE_URL
# asyncpg wants the +asyncpg dialect prefix.
if _db_url.startswith("postgresql://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgresql://") :]
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
