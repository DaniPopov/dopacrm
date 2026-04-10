"""SQLAlchemy ORM model for the ``users`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class UserORM(Base):
    """Dashboard users — owners, staff, sales, and the platform super_admin.

    ``tenant_id`` is **nullable** so super_admin rows can exist with no
    tenant. Per-tenant uniqueness is enforced by ``uq_users_email_tenant``;
    super_admins (where ``tenant_id IS NULL``) get a separate partial unique
    index on ``email`` so two super_admins can't share the same email either.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_users_tenant_id", ondelete="CASCADE"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_users_email_tenant"),
        CheckConstraint(
            "role IN ('super_admin', 'owner', 'staff', 'sales')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "oauth_provider IS NULL OR oauth_provider IN ('google', 'microsoft')",
            name="ck_users_oauth_provider",
        ),
        Index(
            "ix_users_email_super_admin",
            "email",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )
