"""SQLAlchemy ORM model for ``class_entries``.

Mirrors the migration 1:1 so integration tests' ``create_all`` gets the
same schema alembic produces.
"""

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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class ClassEntryORM(Base):
    """One check-in row. Append-only with undone_at soft-delete."""

    __tablename__ = "class_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_entries_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id", name="fk_entries_member_id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            name="fk_entries_subscription_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    class_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classes.id", name="fk_entries_class_id", ondelete="RESTRICT"),
        nullable=False,
    )

    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    entered_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_entries_entered_by", ondelete="SET NULL"),
        nullable=True,
    )

    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_entries_undone_by", ondelete="SET NULL"),
        nullable=True,
    )
    undone_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    override: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    override_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Coach attribution — set server-side at insert by the attendance
    # service (weekday lookup). Immutable once written; correction goes
    # through POST /attendance/{id}/reassign-coach. Nullable so a check-in
    # that can't find a matching coach still records.
    coach_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("coaches.id", name="fk_entries_coach_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "override_kind IS NULL OR override_kind IN ('quota_exceeded', 'not_covered')",
            name="ck_entries_override_kind",
        ),
        CheckConstraint(
            "(override = false AND override_kind IS NULL) "
            "OR (override = true AND override_kind IS NOT NULL)",
            name="ck_entries_override_shape",
        ),
        CheckConstraint(
            "(undone_at IS NULL AND undone_by IS NULL) OR (undone_at IS NOT NULL)",
            name="ck_entries_undone_shape",
        ),
        Index(
            "ix_entries_tenant_entered",
            "tenant_id",
            text("entered_at DESC"),
        ),
        Index(
            "ix_entries_member_recent",
            "member_id",
            text("entered_at DESC"),
        ),
        Index(
            "ix_entries_subscription",
            "subscription_id",
            text("entered_at DESC"),
        ),
        Index(
            "ix_entries_effective",
            "member_id",
            "class_id",
            "entered_at",
            postgresql_where=text("undone_at IS NULL"),
        ),
        Index(
            "ix_entries_coach_entered",
            "coach_id",
            text("entered_at DESC"),
            postgresql_where=text("undone_at IS NULL AND coach_id IS NOT NULL"),
        ),
    )
