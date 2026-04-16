"""create classes table (gym class-types catalog)

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16 10:00:00.000000

First of the three tables outlined in docs/features/classes.md. Passes
and attendance land in later migrations after Plans, Subscriptions,
and Payments are in place.

``classes`` is the gym's catalog of class TYPES: "Spinning", "Pilates",
"CrossFit", "Yoga", etc. Each tenant defines their own. Plans's
plan_entitlements table (next feature) and eventually class_passes FK
into this table — that's why classes-catalog ships first.

Design notes:
- ``name`` unique per tenant (owner can't create two "Yoga" rows in
  the same gym). Cross-tenant duplicates are fine.
- ``is_active`` soft-deactivation — existing entitlements/passes keep
  pointing at deactivated classes (historical reporting survives),
  but new subscriptions/passes can't reference them.
- FK from tenants ``ON DELETE CASCADE`` — nuking a tenant wipes its
  classes too. (We don't hard-delete tenants in v1, only soft-cancel,
  but the FK stays honest.)
- ``color`` is a free-text hint for dashboard/UI (hex code recommended,
  not enforced). Owner picks; UI has a default fallback.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_classes_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint("tenant_id", "name", name="uq_classes_tenant_name"),
    )
    op.create_index("ix_classes_tenant", "classes", ["tenant_id"])
    op.create_index(
        "ix_classes_tenant_active",
        "classes",
        ["tenant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_classes_tenant_active", table_name="classes")
    op.drop_index("ix_classes_tenant", table_name="classes")
    op.drop_table("classes")
