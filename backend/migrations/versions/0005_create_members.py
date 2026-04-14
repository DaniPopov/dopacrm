"""create members table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-14 20:30:00.000000

Creates the ``members`` table — the gym's customers. Members belong to
exactly one tenant and are managed by gym staff. They never log in (no
password_hash, no users row).

Schema highlights:
- ``status`` text with CHECK constraint (active / frozen / cancelled / expired).
- ``custom_fields`` JSONB — per-tenant free-form data (belt color, injury notes, …).
  NOT meant for anything queryable — use a real table for that. See
  docs/features/classes.md for the class pass + attendance model.
- UNIQUE (tenant_id, phone) — same phone can belong to two gyms, but
  never twice within one gym (prevents manual-entry duplicates).
- Indexes on (tenant_id) and (tenant_id, status) for the dashboard
  "active members" query; ON DELETE CASCADE from tenants so wiping a
  tenant wipes their members.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_members_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "join_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("current_date"),
        ),
        sa.Column("frozen_at", sa.Date(), nullable=True),
        sa.Column("frozen_until", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "custom_fields",
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
        sa.CheckConstraint(
            "status IN ('active', 'frozen', 'cancelled', 'expired')",
            name="ck_members_status",
        ),
        sa.UniqueConstraint("tenant_id", "phone", name="uq_members_tenant_phone"),
    )
    op.create_index("ix_members_tenant", "members", ["tenant_id"])
    op.create_index("ix_members_tenant_status", "members", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_members_tenant_status", table_name="members")
    op.drop_index("ix_members_tenant", table_name="members")
    op.drop_table("members")
