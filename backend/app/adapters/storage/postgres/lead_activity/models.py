"""SQLAlchemy ORM model for the ``lead_activities`` table.

Append-only timeline child of ``leads``. ``tenant_id`` is denormalized
so cross-tenant scoping doesn't need a JOIN to ``leads`` on every read
— matches the pattern used elsewhere where activity-style tables
duplicate the tenant FK for fast filtering.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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


class LeadActivityORM(Base):
    __tablename__ = "lead_activities"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_lead_activities_tenant_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "leads.id",
            name="fk_lead_activities_lead_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_lead_activities_created_by",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('call', 'email', 'note', 'meeting', 'status_change')",
            name="ck_lead_activities_type",
        ),
        Index(
            "ix_lead_activities_lead_created",
            "lead_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_lead_activities_tenant_created",
            "tenant_id",
            text("created_at DESC"),
        ),
    )
