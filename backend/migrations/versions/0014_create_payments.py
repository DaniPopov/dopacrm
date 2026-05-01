"""create payments table — append-only revenue ledger

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-30 09:00:00.000000

Payments are the gym's revenue ledger:

- One row per collected payment (cash, card charge, bank transfer, ...).
- Tied to a member (always) and a subscription (optional — drop-in
  payments don't have one).
- ``amount_cents`` is **signed** — positive for collected money, negative
  for refund rows. ``bigint`` so a single tenant's lifetime sum never
  overflows. CHECK ensures non-zero (zero rows mean nothing).
- ``paid_at`` is when the money actually moved; ``created_at`` is when
  the row was entered. Dashboard reports use ``paid_at``.
- Refunds are append-only negative rows pointing at the original via
  ``refund_of_payment_id``. CHECK enforces that refund rows are
  negative.
- ``external_ref`` is reserved for Phase 5 processor integrations
  (Stripe charge id, Israeli credit clearing ref, etc.) — no
  uniqueness constraint because gateways occasionally retry; service
  layer dedupes when the integration ships.

See ``docs/features/payments.md`` for the full design.

Payments is a **basic feature** (always on, not gated). No
``tenants.features_enabled`` change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_payments_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT — preserve payment history if a member is hard-deleted.
        # We don't actually hard-delete members today (status='cancelled' is soft),
        # so this is a safety net for future code that does.
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", name="fk_payments_member_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # SET NULL — drop-ins / one-offs don't have a sub; subs can be
        # cancelled but the payment record stays.
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_payments_subscription_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        # Signed: positive = collected, negative = refund.
        # bigint covers a tenant's lifetime sum without overflow.
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        # Snapshot from tenants.currency at insert time.
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("payment_method", sa.Text(), nullable=False),
        # When the money actually moved (member's perspective). Backdate-able.
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        # Refund chain pointer.
        sa.Column(
            "refund_of_payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payments.id",
                name="fk_payments_refund_of",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        # Reserved for Phase 5 (Stripe charge id, bank transfer ref, ...).
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column(
            "recorded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                name="fk_payments_recorded_by",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "payment_method IN ('cash', 'credit_card', 'standing_order', 'other')",
            name="ck_payments_method",
        ),
        # Zero-amount rows mean nothing — service rejects them too.
        sa.CheckConstraint("amount_cents <> 0", name="ck_payments_amount_nonzero"),
        # Refund rows must be negative (the service flips the sign before insert).
        sa.CheckConstraint(
            "(refund_of_payment_id IS NULL) OR (amount_cents < 0)",
            name="ck_payments_refund_negative",
        ),
    )
    # Dashboard: "revenue this month" + "by month" range scans.
    op.create_index(
        "ix_payments_tenant_paid",
        "payments",
        ["tenant_id", sa.text("paid_at DESC")],
    )
    # Member detail page payment history.
    op.create_index(
        "ix_payments_member_paid",
        "payments",
        ["member_id", sa.text("paid_at DESC")],
    )
    # Per-sub revenue rollups (only meaningful for non-NULL).
    op.create_index(
        "ix_payments_subscription",
        "payments",
        ["subscription_id", sa.text("paid_at DESC")],
        postgresql_where=sa.text("subscription_id IS NOT NULL"),
    )
    # List refunds on a specific payment (only meaningful for refund rows).
    op.create_index(
        "ix_payments_refund_of",
        "payments",
        ["refund_of_payment_id"],
        postgresql_where=sa.text("refund_of_payment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_payments_refund_of", table_name="payments")
    op.drop_index("ix_payments_subscription", table_name="payments")
    op.drop_index("ix_payments_member_paid", table_name="payments")
    op.drop_index("ix_payments_tenant_paid", table_name="payments")
    op.drop_table("payments")
