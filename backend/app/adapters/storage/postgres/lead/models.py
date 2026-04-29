"""SQLAlchemy ORM model for the ``leads`` table.

Status is stored as ``Text`` (with a CHECK constraint at the DB level)
rather than ``sa.Enum`` so we can swap the allowed values via a future
migration without an enum-rename dance — matches Coach + Subscription.

Three index columns drive every read:

- ``(tenant_id, status)`` — Kanban bucketing + dashboard pipeline widget
- ``(tenant_id, assigned_to)`` partial — per-rep lookups (cheap when the
  Phase 4 "sales sees only assigned" toggle ships)
- ``(tenant_id, created_at DESC)`` — default list ordering
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class LeadORM(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_leads_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'other'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))

    assigned_to: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_leads_assigned_to", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    converted_member_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "members.id",
            name="fk_leads_converted_member_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    custom_fields: Mapped[dict[str, Any]] = mapped_column(
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

    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'contacted', 'trial', 'converted', 'lost')",
            name="ck_leads_status",
        ),
        CheckConstraint(
            "source IN ('walk_in', 'website', 'referral', 'social_media', 'ad', 'other')",
            name="ck_leads_source",
        ),
        CheckConstraint(
            "(status = 'converted') = (converted_member_id IS NOT NULL)",
            name="ck_leads_converted_consistency",
        ),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index(
            "ix_leads_tenant_assigned",
            "tenant_id",
            "assigned_to",
            postgresql_where=text("assigned_to IS NOT NULL"),
        ),
        Index("ix_leads_tenant_created", "tenant_id", text("created_at DESC")),
    )
