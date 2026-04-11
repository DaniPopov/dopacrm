"""expand tenants and users for full registration flow

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-11 12:00:00.000000

Adds everything needed for the expanded tenant registration form:
- tenants: saas_plan_id (FK), logo_url, business email, website, full address,
  legal name, tax ID
- users: first_name, last_name, phone (owner info)

The ``saas_plan_id`` column is added as nullable first, backfilled with
the default plan's ID, then switched to NOT NULL. This keeps any
existing tenants working while enforcing the FK for new rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── tenants ──────────────────────────────────────────────────────────────

    # SaaS plan FK — add as nullable, backfill, then enforce NOT NULL
    op.add_column(
        "tenants",
        sa.Column("saas_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tenants_saas_plan_id",
        "tenants",
        "saas_plans",
        ["saas_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "UPDATE tenants SET saas_plan_id = (SELECT id FROM saas_plans WHERE code = 'default')"
    )
    op.alter_column("tenants", "saas_plan_id", nullable=False)

    # Branding
    op.add_column("tenants", sa.Column("logo_url", sa.String(), nullable=True))

    # Contact
    op.add_column("tenants", sa.Column("email", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("website", sa.String(), nullable=True))

    # Address
    op.add_column("tenants", sa.Column("address_street", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("address_city", sa.String(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "address_country",
            sa.String(),
            nullable=True,
            server_default="IL",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("address_postal_code", sa.String(), nullable=True),
    )

    # Legal
    op.add_column("tenants", sa.Column("legal_name", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("tax_id", sa.String(), nullable=True))

    # ── users ────────────────────────────────────────────────────────────────
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(), nullable=True))


def downgrade() -> None:
    # users
    op.drop_column("users", "phone")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

    # tenants — drop in reverse order
    op.drop_column("tenants", "tax_id")
    op.drop_column("tenants", "legal_name")
    op.drop_column("tenants", "address_postal_code")
    op.drop_column("tenants", "address_country")
    op.drop_column("tenants", "address_city")
    op.drop_column("tenants", "address_street")
    op.drop_column("tenants", "website")
    op.drop_column("tenants", "email")
    op.drop_column("tenants", "logo_url")
    op.drop_constraint("fk_tenants_saas_plan_id", "tenants", type_="foreignkey")
    op.drop_column("tenants", "saas_plan_id")
