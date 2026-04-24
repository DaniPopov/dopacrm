"""SQLAlchemy ORM for ``class_sessions`` — materialized calendar rows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class ClassSessionORM(Base):
    __tablename__ = "class_sessions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_sessions_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    class_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classes.id", name="fk_sessions_class_id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "class_schedule_templates.id",
            name="fk_sessions_template_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    head_coach_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "coaches.id", name="fk_sessions_head_coach_id", ondelete="SET NULL"
        ),
        nullable=True,
    )
    assistant_coach_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "coaches.id",
            name="fk_sessions_assistant_coach_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'scheduled'")
    )
    is_customized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_sessions_cancelled_by", ondelete="SET NULL"
        ),
        nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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
            "status IN ('scheduled', 'cancelled')", name="ck_sessions_status"
        ),
        CheckConstraint("ends_at > starts_at", name="ck_sessions_time_order"),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_sessions_cancelled_shape",
        ),
        Index(
            "ix_sessions_tenant_range",
            "tenant_id",
            "starts_at",
            postgresql_where=text("status = 'scheduled'"),
        ),
        Index(
            "ix_sessions_class_starts",
            "class_id",
            "starts_at",
            "status",
        ),
        Index(
            "ix_sessions_head_coach",
            "head_coach_id",
            "starts_at",
            postgresql_where=text(
                "status = 'scheduled' AND head_coach_id IS NOT NULL"
            ),
        ),
        Index(
            "ux_sessions_template_starts",
            "template_id",
            "starts_at",
            unique=True,
            postgresql_where=text("template_id IS NOT NULL"),
        ),
    )
