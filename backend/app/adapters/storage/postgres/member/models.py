"""SQLAlchemy ORM model for the ``members`` table."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class MemberORM(Base):
    """Gym members — the core entity of the CRM.

    Members belong to exactly one tenant (``tenant_id`` NOT NULL). Phone
    is unique within a tenant but not across tenants — a single person
    can be a member of two gyms with the same phone.
    """

    __tablename__ = "members"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_members_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
    join_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("current_date")
    )
    frozen_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    frozen_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "phone", name="uq_members_tenant_phone"),
        CheckConstraint(
            "status IN ('active', 'frozen', 'cancelled', 'expired')",
            name="ck_members_status",
        ),
        Index("ix_members_tenant", "tenant_id"),
        Index("ix_members_tenant_status", "tenant_id", "status"),
    )
