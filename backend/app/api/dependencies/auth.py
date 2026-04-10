"""FastAPI dependencies for authentication and authorization.

Supports two token sources (checked in order):
1. HttpOnly cookie ``access_token`` — used by the React frontend
2. Authorization: Bearer header — used by Swagger, API clients, mobile

On every request, the token's ``jti`` is checked against the Redis
blacklist. Logged-out tokens are rejected even before expiry.
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import TokenPayload, decode_access_token
from app.core.token_blacklist import is_blacklisted
from app.domain.entities.user import Role

#: Bearer scheme with auto_error=False so we can fall back to cookie.
bearer_scheme = HTTPBearer(auto_error=False)

COOKIE_NAME = "access_token"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenPayload:
    """Extract JWT from cookie or header. Raises 401 if missing/invalid/blacklisted."""
    settings = get_settings()

    # 1. Try HttpOnly cookie first (frontend)
    token = request.cookies.get(COOKIE_NAME)

    # 2. Fall back to Authorization header (Swagger, API clients)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(
            token,
            secret_key=settings.APP_SECRET_KEY.get_secret_value(),
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    # 3. Check Redis blacklist (logged-out tokens)
    if payload.jti and await is_blacklisted(payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return payload


def require_role(*allowed_roles: Role) -> Callable:
    """Return a dependency that checks the current user has one of the allowed roles."""

    async def _check(
        user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        if user.role not in [r.value for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check


require_super_admin = require_role(Role.SUPER_ADMIN)
require_owner = require_role(Role.SUPER_ADMIN, Role.OWNER)
require_staff = require_role(Role.SUPER_ADMIN, Role.OWNER, Role.STAFF)
