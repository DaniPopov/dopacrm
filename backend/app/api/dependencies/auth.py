"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import TokenPayload, decode_access_token
from app.domain.entities.user import Role

#: Simple Bearer token scheme — Swagger shows one "Bearer token" input field.
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    """Decode the JWT and return the payload. Raises 401 on invalid/expired token."""
    settings = get_settings()
    try:
        return decode_access_token(
            credentials.credentials,
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
