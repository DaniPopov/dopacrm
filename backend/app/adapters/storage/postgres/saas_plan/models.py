"""SQLAlchemy ORM model for the ``saas_plans`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class SaasPlanORM(Base):
    """DopaCRM pricing tiers — what gyms pay us for.

    Seeded with one plan in migration 0003 (``default`` — 500 ILS, 1000 members).
    """

    __tablename__ = "saas_plans"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'ILS'"))
    billing_period: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'monthly'"),
    )
    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    max_staff_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
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
        UniqueConstraint("code", name="uq_saas_plans_code"),
        CheckConstraint(
            "billing_period IN ('monthly', 'yearly')",
            name="ck_saas_plans_billing_period",
        ),
        CheckConstraint("price_cents >= 0", name="ck_saas_plans_price_nonneg"),
        CheckConstraint("max_members >= 0", name="ck_saas_plans_max_members_nonneg"),
    )
