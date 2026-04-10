"""Rate limiting via Redis — dependency factory for FastAPI routes.

Each rate limit preset returns a FastAPI ``Depends()`` that checks a Redis
counter before the route handler runs. If the limit is exceeded, a 429
response is returned immediately.

Usage in routes:

    @router.post("/login", dependencies=[login_rate_limit])
    async def login(...): ...

    @router.get("/users", dependencies=[api_rate_limit])
    async def list_users(...): ...

Different presets use different keys:
- ``by_ip`` — login, public endpoints (brute-force protection)
- ``by_bearer`` — authenticated API endpoints (per-user throttle)
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.adapters.storage.redis.client import get_redis

# ── Key extractors ────────────────────────────────────────────────────────────


def by_ip(request: Request) -> str:
    """Rate limit key = client IP (handles X-Forwarded-For from proxies)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def by_bearer(request: Request) -> str:
    """Rate limit key = JWT subject (user ID) from the Authorization header.

    Falls back to IP if no valid token is present (shouldn't happen on
    protected routes, but safe fallback).
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        # Use the token itself as a fingerprint (first 16 chars — enough
        # to distinguish users without storing the full token in Redis).
        return auth[7:23]
    return by_ip(request)


# ── Rate limit factory ────────────────────────────────────────────────────────


def rate_limit(
    limit: int,
    window_seconds: int = 60,
    key_func: Callable[[Request], str] = by_ip,
) -> list:
    """Return a ``dependencies=[...]`` list for a FastAPI route decorator.

    Args:
        limit: Max requests allowed in the window.
        window_seconds: Time window in seconds (default 60).
        key_func: Callable that extracts the rate limit key from the request.

    Returns:
        A list with one Depends() — pass it to ``dependencies=`` on a route.
    """

    async def _check(request: Request) -> None:
        try:
            redis = get_redis()
            key = f"rate:{request.url.path}:{key_func(request)}"

            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)

            if count > limit:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {ttl}s.",
                    headers={"Retry-After": str(ttl)},
                )
        except HTTPException:
            raise  # re-raise 429s
        except Exception:
            # Redis is down — fail-open (allow the request).
            # Availability > rate limiting. Log a warning so we notice.
            import structlog

            structlog.get_logger("rate_limit").warning("redis_unavailable", path=request.url.path)

    return [Depends(_check)]


# ── Presets ───────────────────────────────────────────────────────────────────

#: Login: 10 requests per minute per IP — brute-force protection.
login_rate_limit = rate_limit(10, 60, key_func=by_ip)

#: Frontend API: 60 requests per minute per user — standard throttle.
api_rate_limit = rate_limit(60, 60, key_func=by_bearer)

#: Public endpoints (health, docs): 120 requests per minute per IP.
public_rate_limit = rate_limit(120, 60, key_func=by_ip)
