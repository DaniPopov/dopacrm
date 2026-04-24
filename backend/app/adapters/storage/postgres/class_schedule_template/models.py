"""SQLAlchemy ORM model for ``class_schedule_templates``.

Templates are recurring rules that materialize into ``class_sessions``.
Mirrors migration 0012 1:1 so ``create_all`` under integration-test
fixtures produces the same schema Alembic ships.
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class ClassScheduleTemplateORM(Base):
    __tablename__ = "class_schedule_templates"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id", name="fk_sched_templates_tenant_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    class_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "classes.id", name="fk_sched_templates_class_id", ondelete="CASCADE"
        ),
        nullable=False,
    )

    weekdays: Mapped[list[str]] = mapped_column(ARRAY(TEXT), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    head_coach_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "coaches.id",
            name="fk_sched_templates_head_coach_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    assistant_coach_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "coaches.id",
            name="fk_sched_templates_assistant_coach_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    starts_on: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
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
            "cardinality(weekdays) > 0", name="ck_sched_templates_weekdays_nonempty"
        ),
        CheckConstraint("end_time > start_time", name="ck_sched_templates_time_order"),
        CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_sched_templates_range_valid",
        ),
        Index("ix_sched_templates_tenant_class", "tenant_id", "class_id"),
        Index(
            "ix_sched_templates_active",
            "tenant_id",
            postgresql_where=text("is_active"),
        ),
    )
