"""SQLAlchemy ORM model for the ``payments`` table.

Append-only revenue ledger. Signed ``amount_cents`` (BigInteger so
lifetime tenant sums don't overflow), ``payment_method`` stored as
Text with a CHECK at the DB level (matches the Coach/Schedule
pattern of avoiding sa.Enum so we can swap values without an enum
rename dance), ``refund_of_payment_id`` self-FK for refund chains.

No ``updated_at`` column — payments are immutable. ``created_at``
is the only timestamp the row carries beyond ``paid_at``.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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


class PaymentORM(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_payments_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id", name="fk_payments_member_id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            name="fk_payments_subscription_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    refund_of_payment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payments.id", name="fk_payments_refund_of", ondelete="RESTRICT"),
        nullable=True,
    )
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    recorded_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_payments_recorded_by", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('cash', 'credit_card', 'standing_order', 'other')",
            name="ck_payments_method",
        ),
        CheckConstraint("amount_cents <> 0", name="ck_payments_amount_nonzero"),
        CheckConstraint(
            "(refund_of_payment_id IS NULL) OR (amount_cents < 0)",
            name="ck_payments_refund_negative",
        ),
        Index("ix_payments_tenant_paid", "tenant_id", text("paid_at DESC")),
        Index("ix_payments_member_paid", "member_id", text("paid_at DESC")),
        Index(
            "ix_payments_subscription",
            "subscription_id",
            text("paid_at DESC"),
            postgresql_where=text("subscription_id IS NOT NULL"),
        ),
        Index(
            "ix_payments_refund_of",
            "refund_of_payment_id",
            postgresql_where=text("refund_of_payment_id IS NOT NULL"),
        ),
    )
