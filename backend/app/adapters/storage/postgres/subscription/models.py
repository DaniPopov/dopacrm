"""SQLAlchemy ORM models for ``subscriptions`` + ``subscription_events``.

Kept next to the Subscription repository (``../subscription``) — shared
module because the two tables are always read together (the member
detail timeline, the owner retention dashboard).

All table-level constraints mirror the Alembic migration in
``0008_create_subscriptions``. The migration is the source of truth for
DDL; these classes describe the same shape in Python so SQLAlchemy can
emit queries and the test suite can create tables in integration tests.
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
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.storage.postgres.database import Base


class SubscriptionORM(Base):
    """The commercial link between a Member and a Plan."""

    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_subs_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id", name="fk_subs_member_id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("membership_plans.id", name="fk_subs_plan_id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    started_at: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    frozen_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    frozen_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    expired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaced_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            name="fk_subs_replaced_by_id",
            ondelete="SET NULL",
        ),
        nullable=True,
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

    # No ORM relationship to events — all event reads go through the repo's
    # explicit list_events() query. Keeps async flushes from triggering
    # implicit lazy loads on the events collection.

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'frozen', 'expired', 'cancelled', 'replaced')",
            name="ck_subs_status",
        ),
        CheckConstraint("price_cents >= 0", name="ck_subs_price_non_negative"),
        CheckConstraint(
            "(status <> 'frozen' AND frozen_at IS NULL AND frozen_until IS NULL) "
            "OR (status = 'frozen' AND frozen_at IS NOT NULL)",
            name="ck_subs_frozen_shape",
        ),
        CheckConstraint(
            "(status <> 'cancelled' AND cancelled_at IS NULL) "
            "OR (status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_subs_cancelled_shape",
        ),
        # See migration note — replaced_by_id enforced by service, not row CHECK.
        CheckConstraint(
            "(status <> 'replaced' AND replaced_at IS NULL AND replaced_by_id IS NULL) "
            "OR (status = 'replaced' AND replaced_at IS NOT NULL)",
            name="ck_subs_replaced_shape",
        ),
        CheckConstraint(
            "frozen_until IS NULL OR frozen_at IS NULL OR frozen_until >= frozen_at",
            name="ck_subs_frozen_until_after_start",
        ),
        # Partial UNIQUE — at most one live (active|frozen) sub per member.
        # The DB is the authority; the service pre-checks for nicer errors.
        Index(
            "uq_subs_one_live_per_member",
            "member_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'frozen')"),
        ),
        Index("ix_subs_tenant_status", "tenant_id", "status"),
        Index("ix_subs_member_created", "member_id", text("created_at DESC")),
        Index(
            "ix_subs_expires_due",
            "tenant_id",
            "expires_at",
            postgresql_where=text("status = 'active' AND expires_at IS NOT NULL"),
        ),
        Index(
            "ix_subs_frozen_until_due",
            "tenant_id",
            "frozen_until",
            postgresql_where=text("status = 'frozen' AND frozen_until IS NOT NULL"),
        ),
    )


class SubscriptionEventORM(Base):
    """Append-only timeline row. One per state transition.

    Written inside the same transaction as the subscription mutation.
    ``created_by`` is nullable: NULL = system event (the nightly
    auto-unfreeze / auto-expire jobs).
    """

    __tablename__ = "subscription_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_sub_events_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            name="fk_sub_events_subscription_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_sub_events_created_by", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'created', 'frozen', 'unfrozen', 'expired', "
            "'renewed', 'replaced', 'changed_plan', 'cancelled'"
            ")",
            name="ck_sub_events_type",
        ),
        Index(
            "ix_sub_events_sub_occurred",
            "subscription_id",
            text("occurred_at DESC"),
        ),
        Index(
            "ix_sub_events_tenant_type",
            "tenant_id",
            "event_type",
            text("occurred_at DESC"),
        ),
    )
