"""Stateless security utilities — password hashing and JWT.

Pure infrastructure: no database calls, no business logic, no imports
from ``services/`` or ``adapters/``. Used by ``services/auth_service.py``
for orchestration and by ``api/dependencies/auth.py`` for token validation.

Password hashing: argon2id (OWASP recommended).
JWT: HS256 signed with APP_SECRET_KEY, 8-hour access tokens.
Each token carries a ``jti`` (JWT ID) — a unique identifier used for
the Redis blacklist on logout.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pydantic import BaseModel

from app.core.time import utcnow

if TYPE_CHECKING:
    from uuid import UUID

#: Shared argon2 hasher — thread-safe, reusable across requests.
_hasher = PasswordHasher()

#: JWT defaults
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(hours=8)
REFRESH_TOKEN_EXPIRE = timedelta(days=30)


# ── Password hashing ─────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return an argon2id hash. Store the result in ``users.password_hash``."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches ``hashed``. No exception on mismatch."""
    try:
        _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """True if the hash uses outdated params and should be regenerated on next login."""
    return _hasher.check_needs_rehash(hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


class TokenPayload(BaseModel):
    """Decoded JWT payload — what ``decode_access_token`` returns."""

    sub: str  # user ID (UUID as string)
    role: str
    tenant_id: str | None = None
    jti: str | None = None  # JWT ID — used for blacklist on logout
    type: str = "access"  # access | refresh
    exp: int | None = None  # expiry timestamp (epoch seconds)


def create_access_token(
    *,
    user_id: UUID,
    role: str,
    tenant_id: UUID | None,
    secret_key: str,
    expires_delta: timedelta = ACCESS_TOKEN_EXPIRE,
) -> str:
    """Create a signed HS256 JWT access token with a unique jti."""
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "type": "access",
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    *,
    user_id: UUID,
    secret_key: str,
    expires_delta: timedelta = REFRESH_TOKEN_EXPIRE,
) -> str:
    """Create a signed HS256 JWT refresh token (minimal payload)."""
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret_key: str) -> TokenPayload:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on failure."""
    data = jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    return TokenPayload(**data)
