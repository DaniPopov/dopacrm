"""SQLAlchemy ORM model for the ``class_coaches`` link table.

Many-to-many between classes and coaches, with per-link pay rules and
a weekday teaching pattern. See ``docs/features/coaches.md`` for the
full model.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class ClassCoachORM(Base):
    __tablename__ = "class_coaches"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_class_coaches_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    class_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classes.id", name="fk_class_coaches_class_id", ondelete="CASCADE"),
        nullable=False,
    )
    coach_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("coaches.id", name="fk_class_coaches_coach_id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ראשי'"))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    pay_model: Mapped[str] = mapped_column(Text, nullable=False)
    pay_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    weekdays: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )

    starts_on: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

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
            "pay_model IN ('fixed', 'per_session', 'per_attendance')",
            name="ck_class_coaches_pay_model",
        ),
        CheckConstraint(
            "pay_amount_cents >= 0",
            name="ck_class_coaches_pay_amount_nonneg",
        ),
        CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_class_coaches_range_valid",
        ),
        UniqueConstraint("class_id", "coach_id", "role", name="ux_class_coaches_role"),
        Index("ix_class_coaches_tenant", "tenant_id"),
        Index("ix_class_coaches_class", "class_id"),
        Index("ix_class_coaches_coach", "coach_id"),
    )
