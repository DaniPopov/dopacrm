"""SQLAlchemy ORM model for the ``tenants`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class TenantORM(Base):
    """Tenants (gyms) are the top-level account entity.

    The ``slug`` links to the matching tenant config document in
    MongoDB. ``status`` is a text enum (trial/active/suspended/cancelled).
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))

    # SaaS plan — every tenant must be on one
    saas_plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("saas_plans.id", name="fk_tenants_saas_plan_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Branding
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # Contact
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)

    # Address
    address_street: Mapped[str | None] = mapped_column(String, nullable=True)
    address_city: Mapped[str | None] = mapped_column(String, nullable=True)
    address_country: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        server_default=text("'IL'"),
    )
    address_postal_code: Mapped[str | None] = mapped_column(String, nullable=True)

    # Legal
    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Regional
    timezone: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'Asia/Jerusalem'"),
    )
    currency: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'ILS'"))
    locale: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'he-IL'"))

    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        UniqueConstraint("slug", name="uq_tenants_slug"),
        CheckConstraint(
            "status IN ('trial', 'active', 'suspended', 'cancelled')",
            name="ck_tenants_status",
        ),
    )
