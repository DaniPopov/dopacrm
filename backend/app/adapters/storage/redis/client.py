"""Redis async client — singleton connection pool.

Lazy: the client is created on first call to ``get_redis()``, not on import.
Uses the ``REDIS_URL`` from app settings.
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    """Return a cached async Redis client bound to REDIS_URL."""
    settings = get_settings()
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
