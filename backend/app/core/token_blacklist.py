"""Redis-based JWT blacklist for logout.

When a user logs out, their token's ``jti`` is added to Redis with a TTL
matching the remaining token expiry. On every authenticated request, the
auth dependency checks if the jti is blacklisted.

Redis key format: ``blacklist:{jti}``
TTL: remaining seconds until token expiry (auto-cleaned by Redis).

Fail-open: if Redis is unreachable, the blacklist check is skipped.
This matches the rate limiter's behavior — we don't block all auth
because Redis is down.
"""

from __future__ import annotations

from app.adapters.storage.redis.client import get_redis
from app.core.logger import get_logger
from app.core.time import utcnow

logger = get_logger(__name__)

_PREFIX = "blacklist:"


async def blacklist_token(jti: str, exp_timestamp: int) -> None:
    """Add a token's jti to the blacklist until it expires.

    Args:
        jti: The JWT ID from the token payload.
        exp_timestamp: The token's ``exp`` claim (epoch seconds).
    """
    now = int(utcnow().timestamp())
    ttl = exp_timestamp - now

    if ttl <= 0:
        # Token already expired — no need to blacklist
        return

    try:
        redis = get_redis()
        await redis.setex(f"{_PREFIX}{jti}", ttl, "1")
        logger.info("token_blacklisted", jti=jti, ttl_seconds=ttl)
    except Exception:
        logger.warning("token_blacklist_failed", jti=jti, reason="redis_unavailable")


async def is_blacklisted(jti: str) -> bool:
    """Check if a token's jti is in the blacklist.

    Returns False (fail-open) if Redis is unreachable.
    """
    try:
        redis = get_redis()
        return await redis.exists(f"{_PREFIX}{jti}") > 0
    except Exception:
        logger.warning("blacklist_check_failed", jti=jti, reason="redis_unavailable")
        return False
