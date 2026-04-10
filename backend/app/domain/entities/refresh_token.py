"""Pydantic domain entity for refresh tokens (JWT session rows)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RefreshToken(BaseModel):
    """One active session on one device.

    The raw token is never stored — only the hash, which lives inside the
    repository and never crosses the entity boundary. Read entities only
    expose metadata (when it expires, who it belongs to, whether it's
    been revoked).
    """

    id: UUID
    user_id: UUID
    expires_at: datetime
    is_revoked: bool
    created_at: datetime
