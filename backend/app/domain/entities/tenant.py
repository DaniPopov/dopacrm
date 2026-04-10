"""Pydantic domain entity for tenants (gym accounts)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Tenant(BaseModel):
    """A registered gym on the platform — the top-level tenant.

    Stored in Postgres. The ``slug`` links to the corresponding
    tenant config document in MongoDB. ``is_active`` reflects the
    raw boolean ``status`` column at the persistence layer (the repo
    translates between the two names).
    """

    id: UUID
    slug: str
    name: str
    phone: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
