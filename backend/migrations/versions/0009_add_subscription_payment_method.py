"""add payment_method + payment_method_detail to subscriptions

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-17 17:00:00.000000

Closes a gap in the cash-vs-card model: staff could infer the payment
style from expires_at (set = cash/prepaid, null = standing order), but
it was never explicit on the row or the UI. This adds:

- ``payment_method`` — enum-like TEXT:
    cash           → מזומן
    credit_card    → אשראי
    standing_order → הוראת קבע
    other          → אחר (free text in ``payment_method_detail``)

- ``payment_method_detail`` — free-text elaboration. Nullable. The UI
  requires it when method='other' (captures the whole point of the
  "other" bucket). The DB doesn't enforce that coupling — if staff
  genuinely leaves it blank that's their call.

Existing rows backfill to 'cash'. In IL that's the most common default,
and these are dev-only rows anyway; production starts from a clean slate
when we onboard the first gym.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "payment_method",
            sa.String(length=30),
            nullable=False,
            server_default="cash",
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("payment_method_detail", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_subs_payment_method",
        "subscriptions",
        "payment_method IN ('cash', 'credit_card', 'standing_order', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_subs_payment_method", "subscriptions", type_="check")
    op.drop_column("subscriptions", "payment_method_detail")
    op.drop_column("subscriptions", "payment_method")
