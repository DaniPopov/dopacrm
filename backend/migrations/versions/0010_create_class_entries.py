"""create class_entries table (attendance / check-in)

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-17 21:00:00.000000

The highest-volume write in the CRM — an active member hits it 3-5 times
a week. Designed so the two hot paths stay cheap:

1. "How many times did this member attend this class in the current
   reset window?" — quota enforcement. Answered by the partial index
   on (member_id, class_id, entered_at) WHERE undone_at IS NULL.

2. "Who checked in today?" — dashboard. Answered by the
   (tenant_id, entered_at::date DESC) index.

Soft-delete via ``undone_at`` (NOT a status enum) because an entry has
exactly two states — recorded or undone. No multi-state machine, and
reporting filters love ``WHERE undone_at IS NULL``.

No separate events log table — the row IS the state machine, and the
``entered_by`` / ``undone_by`` / ``undone_reason`` columns capture the
full audit trail. When Attendance proves itself and we need richer
history (multiple undo+redo, sessions, etc.), revisit.

Owner audit is first-class:
- ``override BOOLEAN`` marks entries that bypassed a quota or were on
  a class not in the member's plan. Dashboards bucket by this.
- ``undone_reason TEXT`` captures why staff rolled back, so the owner
  can spot patterns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_entries_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", name="fk_entries_member_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_entries_subscription_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", name="fk_entries_class_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Timestamps: TIMESTAMPTZ for hour-level precision (the 24h undo
        # window depends on it). DATE would be too coarse.
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "entered_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_entries_entered_by", ondelete="SET NULL"),
            nullable=True,
        ),
        # Soft-delete / undo
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "undone_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_entries_undone_by", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("undone_reason", sa.Text(), nullable=True),
        # Override telemetry (staff bypassed a quota or non-covered class).
        # `override_kind` is an enum-ish string:
        #   'quota_exceeded' — entitlement existed but quota was full
        #   'not_covered'    — no entitlement for this class at all
        # Null means "not an override" — the happy path.
        sa.Column(
            "override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("override_kind", sa.String(length=30), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "override_kind IS NULL OR override_kind IN ('quota_exceeded', 'not_covered')",
            name="ck_entries_override_kind",
        ),
        # Shape: if override=false then kind/reason must be null
        sa.CheckConstraint(
            "(override = false AND override_kind IS NULL) "
            "OR (override = true AND override_kind IS NOT NULL)",
            name="ck_entries_override_shape",
        ),
        # Shape: if undone_at is set, undone_by should be too (best-effort)
        sa.CheckConstraint(
            "(undone_at IS NULL AND undone_by IS NULL) OR (undone_at IS NOT NULL)",
            name="ck_entries_undone_shape",
        ),
    )

    # ── Indexes ─────────────────────────────────────────────────────
    # Dashboard "check-ins today" query. Plain tenant_id + timestamp — the
    # caller filters via entered_at >= date_trunc('day', ...). We can't
    # index on `(entered_at::date)` because the cast isn't immutable for
    # TIMESTAMPTZ columns (it depends on session timezone).
    op.create_index(
        "ix_entries_tenant_entered",
        "class_entries",
        ["tenant_id", sa.text("entered_at DESC")],
    )

    # Member detail page: "Dana's last 20 entries".
    op.create_index(
        "ix_entries_member_recent",
        "class_entries",
        ["member_id", sa.text("entered_at DESC")],
    )

    # "All entries for this sub" — used when Payments reconciles a sub's usage.
    op.create_index(
        "ix_entries_subscription",
        "class_entries",
        ["subscription_id", sa.text("entered_at DESC")],
    )

    # The quota-check hot path: effective entries only (filters out undos).
    # Partial index keeps it much smaller than a full index; every
    # quota query filters WHERE undone_at IS NULL.
    op.create_index(
        "ix_entries_effective",
        "class_entries",
        ["member_id", "class_id", "entered_at"],
        postgresql_where=sa.text("undone_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_entries_effective", table_name="class_entries")
    op.drop_index("ix_entries_subscription", table_name="class_entries")
    op.drop_index("ix_entries_member_recent", table_name="class_entries")
    op.drop_index("ix_entries_tenant_entered", table_name="class_entries")
    op.drop_table("class_entries")
