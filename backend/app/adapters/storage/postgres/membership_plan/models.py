"""SQLAlchemy ORM models for ``membership_plans`` + ``plan_entitlements``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class MembershipPlanORM(Base):
    """Catalog of gym offerings. Each tenant defines its own plans."""

    __tablename__ = "membership_plans"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_plans_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    custom_attrs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
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

    # Loaded by the repo when fetching with details. Cascade delete at
    # the ORM level mirrors the DB-level ON DELETE CASCADE.
    entitlements: Mapped[list[PlanEntitlementORM]] = relationship(
        "PlanEntitlementORM",
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint("type IN ('recurring', 'one_time')", name="ck_plans_type"),
        CheckConstraint("price_cents >= 0", name="ck_plans_price_non_negative"),
        CheckConstraint(
            "billing_period IN ('monthly', 'quarterly', 'yearly', 'one_time')",
            name="ck_plans_billing_period",
        ),
        CheckConstraint(
            "duration_days IS NULL OR duration_days > 0",
            name="ck_plans_duration_positive",
        ),
        CheckConstraint(
            "(type = 'recurring' AND duration_days IS NULL "
            "AND billing_period <> 'one_time') "
            "OR (type = 'one_time' AND duration_days IS NOT NULL "
            "AND billing_period = 'one_time')",
            name="ck_plans_shape_integrity",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_plans_tenant_name"),
        Index("ix_plans_tenant", "tenant_id"),
        Index("ix_plans_tenant_active", "tenant_id", "is_active"),
    )


class PlanEntitlementORM(Base):
    """Access-rule row attached to a plan."""

    __tablename__ = "plan_entitlements"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "membership_plans.id",
            name="fk_entitlements_plan_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    class_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classes.id", name="fk_entitlements_class_id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reset_period: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    plan: Mapped[MembershipPlanORM] = relationship(
        "MembershipPlanORM", back_populates="entitlements"
    )

    __table_args__ = (
        CheckConstraint(
            "reset_period IN ('weekly', 'monthly', 'billing_period', 'never', 'unlimited')",
            name="ck_entitlements_reset_period",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_entitlements_quantity_positive",
        ),
        CheckConstraint(
            "(reset_period = 'unlimited' AND quantity IS NULL) "
            "OR (reset_period <> 'unlimited' AND quantity IS NOT NULL)",
            name="ck_entitlements_quantity_shape",
        ),
        Index("ix_entitlements_plan", "plan_id"),
        Index("ix_entitlements_class", "class_id"),
    )
