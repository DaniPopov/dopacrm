"""create membership_plans + plan_entitlements tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-16 12:00:00.000000

Two related tables shipping together:

1. ``membership_plans`` — what the gym sells. Each gym defines its
   own catalog: "Monthly Unlimited", "10-class pack", "Annual
   Student", etc. Name unique within tenant.

2. ``plan_entitlements`` — the access rules a plan grants. A plan
   with zero entitlement rows = unlimited access to any class
   (simplest case: "Monthly Unlimited"). One or more rows = metered:

      {class_id: yoga, quantity: 12, reset: 'monthly'}
      + {class_id: pt,  quantity: 2,  reset: 'monthly'}
      = 12 yoga + 2 PT per month

   class_id NULL = "any class"; reset='unlimited' with quantity=NULL
   = "unlimited for this specific class type".

Check constraints enforce shape integrity at the DB layer so invalid
combinations (one_time plan without duration_days; metered
entitlement without quantity; etc.) can never exist as rows.

Entitlements FK into ``classes.id`` with ON DELETE RESTRICT — you
can't hard-delete a class while it's referenced by any entitlement.
Deactivating a class is the safe path (existing entitlements keep
working, new subscriptions can't reference it — enforced in service).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── membership_plans ─────────────────────────────────────────────────
    op.create_table(
        "membership_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_plans_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("billing_period", sa.String(length=20), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "custom_attrs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("type IN ('recurring', 'one_time')", name="ck_plans_type"),
        sa.CheckConstraint("price_cents >= 0", name="ck_plans_price_non_negative"),
        sa.CheckConstraint(
            "billing_period IN ('monthly', 'quarterly', 'yearly', 'one_time')",
            name="ck_plans_billing_period",
        ),
        sa.CheckConstraint(
            "duration_days IS NULL OR duration_days > 0",
            name="ck_plans_duration_positive",
        ),
        # Shape integrity: recurring plans have no duration_days AND a
        # non-one_time billing period; one_time plans have duration_days
        # AND billing_period='one_time'.
        sa.CheckConstraint(
            "(type = 'recurring' AND duration_days IS NULL "
            "AND billing_period <> 'one_time') "
            "OR (type = 'one_time' AND duration_days IS NOT NULL "
            "AND billing_period = 'one_time')",
            name="ck_plans_shape_integrity",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_plans_tenant_name"),
    )
    op.create_index("ix_plans_tenant", "membership_plans", ["tenant_id"])
    op.create_index(
        "ix_plans_tenant_active",
        "membership_plans",
        ["tenant_id", "is_active"],
    )

    # ── plan_entitlements ────────────────────────────────────────────────
    op.create_table(
        "plan_entitlements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "membership_plans.id",
                name="fk_entitlements_plan_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "classes.id",
                name="fk_entitlements_class_id",
                ondelete="RESTRICT",
            ),
            nullable=True,  # NULL means "any class"
        ),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("reset_period", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "reset_period IN ('weekly', 'monthly', 'billing_period', 'never', 'unlimited')",
            name="ck_entitlements_reset_period",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_entitlements_quantity_positive",
        ),
        # Shape: 'unlimited' has no quantity; all other reset_periods
        # require a quantity.
        sa.CheckConstraint(
            "(reset_period = 'unlimited' AND quantity IS NULL) "
            "OR (reset_period <> 'unlimited' AND quantity IS NOT NULL)",
            name="ck_entitlements_quantity_shape",
        ),
    )
    op.create_index("ix_entitlements_plan", "plan_entitlements", ["plan_id"])
    op.create_index("ix_entitlements_class", "plan_entitlements", ["class_id"])


def downgrade() -> None:
    op.drop_index("ix_entitlements_class", table_name="plan_entitlements")
    op.drop_index("ix_entitlements_plan", table_name="plan_entitlements")
    op.drop_table("plan_entitlements")
    op.drop_index("ix_plans_tenant_active", table_name="membership_plans")
    op.drop_index("ix_plans_tenant", table_name="membership_plans")
    op.drop_table("membership_plans")
