"""expand tenants: status text, timezone, currency, locale, trial_ends_at

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-10 10:00:00.000000

Changes:
- status: boolean → text (trial/active/suspended/cancelled)
- Add: timezone, currency, locale, trial_ends_at
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add new columns
    op.add_column("tenants", sa.Column("timezone", sa.String(), nullable=False, server_default="Asia/Jerusalem"))
    op.add_column("tenants", sa.Column("currency", sa.String(), nullable=False, server_default="ILS"))
    op.add_column("tenants", sa.Column("locale", sa.String(), nullable=False, server_default="he-IL"))
    op.add_column("tenants", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Convert status from boolean to text
    #    true → 'active', false → 'suspended'
    op.add_column("tenants", sa.Column("status_new", sa.String(), nullable=True))
    op.execute("UPDATE tenants SET status_new = CASE WHEN status = true THEN 'active' ELSE 'suspended' END")
    op.drop_column("tenants", "status")
    op.alter_column("tenants", "status_new", new_column_name="status", nullable=False, server_default="active")

    # 3. Add check constraint on status
    op.create_check_constraint(
        "ck_tenants_status",
        "tenants",
        "status IN ('trial', 'active', 'suspended', 'cancelled')",
    )


def downgrade() -> None:
    # Remove check constraint
    op.drop_constraint("ck_tenants_status", "tenants", type_="check")

    # Convert status back to boolean
    op.add_column("tenants", sa.Column("status_old", sa.Boolean(), nullable=True))
    op.execute("UPDATE tenants SET status_old = CASE WHEN status = 'active' THEN true ELSE false END")
    op.drop_column("tenants", "status")
    op.alter_column("tenants", "status_old", new_column_name="status", nullable=False, server_default=sa.text("true"))

    # Drop new columns
    op.drop_column("tenants", "trial_ends_at")
    op.drop_column("tenants", "locale")
    op.drop_column("tenants", "currency")
    op.drop_column("tenants", "timezone")
