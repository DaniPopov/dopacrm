"""create saas_plans

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-11 09:00:00.000000

The SaaS pricing tiers a tenant (gym) subscribes to. In v1 we ship with
one plan (DopaCRM Standard — 500 ILS, 1000 members). The full schema is
intentionally broader so we can add Free/Starter/Pro tiers later without
another migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saas_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="ILS"),
        sa.Column(
            "billing_period",
            sa.String(),
            nullable=False,
            server_default="monthly",
        ),
        sa.Column("max_members", sa.Integer(), nullable=False),
        sa.Column("max_staff_users", sa.Integer(), nullable=True),
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_saas_plans"),
        sa.UniqueConstraint("code", name="uq_saas_plans_code"),
        sa.CheckConstraint(
            "billing_period IN ('monthly', 'yearly')",
            name="ck_saas_plans_billing_period",
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_saas_plans_price_nonneg"),
        sa.CheckConstraint("max_members >= 0", name="ck_saas_plans_max_members_nonneg"),
    )

    # Seed the default plan for the POC.
    op.execute(
        """
        INSERT INTO saas_plans (
            code, name, price_cents, currency, billing_period,
            max_members, max_staff_users, features, is_public
        ) VALUES (
            'default',
            'DopaCRM Standard',
            50000,
            'ILS',
            'monthly',
            1000,
            NULL,
            '{}'::jsonb,
            true
        )
        """,
    )


def downgrade() -> None:
    op.drop_table("saas_plans")
