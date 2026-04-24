"""SQLAlchemy ORM model for the ``coaches`` table.

Optional 1:1 link to a user (``user_id``) — enforced unique via the
partial index ``ux_coaches_user`` (`WHERE user_id IS NOT NULL`). Status
shape-checks mirror Members (frozen iff frozen_at set, cancelled iff
cancelled_at set).
"""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class CoachORM(Base):
    __tablename__ = "coaches"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_coaches_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_coaches_user_id", ondelete="SET NULL"),
        nullable=True,
    )

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)

    hired_at: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    custom_attrs: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

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
        CheckConstraint(
            "status IN ('active', 'frozen', 'cancelled')",
            name="ck_coaches_status",
        ),
        CheckConstraint(
            "(status = 'frozen') = (frozen_at IS NOT NULL)",
            name="ck_coaches_frozen_shape",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_coaches_cancelled_shape",
        ),
        Index("ix_coaches_tenant_status", "tenant_id", "status"),
    )
