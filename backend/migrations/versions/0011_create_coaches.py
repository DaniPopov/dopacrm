"""create coaches + class_coaches + class_entries.coach_id

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-24 08:00:00.000000

Coaches is the first feature that touches the gym's **cost side** —
turns "how much do we make?" into "how much do we net?".

Three DB changes ship together:

1. ``coaches`` — first-class entity for trainers. Optional 1:1 link to
   ``users`` so coaches who want to log in can; coaches who don't still
   exist on payroll. Status machine mirrors Members (active / frozen /
   cancelled) so the owner can freeze a coach on leave without losing
   history.

2. ``class_coaches`` — many-to-many between classes and coaches, with
   **per-link pay rules**. A coach can be "head of boxing at ₪50/attendee"
   AND "assistant in wrestling at ₪30/session" on the same gym. Rate
   changes = end this row (``ends_on = yesterday``) + insert a new one;
   mutating ``pay_amount_cents`` in place rewrites payroll history, so
   the UI prefers the split pattern.

3. ``class_entries.coach_id`` — stamped server-side at check-in via the
   weekday lookup against ``class_coaches``. Immutable: changing
   ``weekdays`` later does NOT rewrite past entries. See
   ``docs/crm_logic.md`` §5 for the full attribution rule.

Also extends ``users.role`` CHECK to accept ``'coach'`` as a system role.
The dynamic-roles feature (Phase 4) will eventually replace the enum
with ``tenant_roles`` — until then we take the enum expansion.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Allow 'coach' in users.role ──────────────────────────────
    # Drop + recreate the CHECK created by 0001. Cheap — no table scan
    # needed since no existing row has role='coach'.
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('super_admin', 'owner', 'staff', 'sales', 'coach')",
    )

    # ── 2. coaches table ────────────────────────────────────────────
    op.create_table(
        "coaches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_coaches_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Optional 1:1 link to a user. Enforced unique via a partial
        # index below — a user can be linked to at most one coach.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_coaches_user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column(
            "hired_at",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "custom_attrs",
            postgresql.JSONB(astext_type=sa.Text()),
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
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'frozen', 'cancelled')",
            name="ck_coaches_status",
        ),
        # Shape: frozen iff frozen_at is set.
        sa.CheckConstraint(
            "(status = 'frozen') = (frozen_at IS NOT NULL)",
            name="ck_coaches_frozen_shape",
        ),
        # Shape: cancelled iff cancelled_at is set.
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_coaches_cancelled_shape",
        ),
    )

    # One user → at most one coach row. NULL allowed freely.
    op.create_index(
        "ux_coaches_user",
        "coaches",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # Owner list queries filter by status (active coaches first).
    op.create_index("ix_coaches_tenant_status", "coaches", ["tenant_id", "status"])

    # ── 3. class_coaches link table ─────────────────────────────────
    op.create_table(
        "class_coaches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenants.id", name="fk_class_coaches_tenant_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "classes.id", name="fk_class_coaches_class_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id", name="fk_class_coaches_coach_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        # Free-form text — owner types "ראשי", "עוזר", "night-shift", etc.
        # Defaults to "ראשי" (head coach) — the most common case.
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'ראשי'"),
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("pay_model", sa.Text(), nullable=False),
        sa.Column("pay_amount_cents", sa.Integer(), nullable=False),
        # Which weekdays this coach teaches this class. Lowercase 3-letter
        # codes: 'sun' .. 'sat'. Empty array = "all days" (coach gets
        # attributed whenever a match is needed).
        sa.Column(
            "weekdays",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "starts_on",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("ends_on", sa.Date(), nullable=True),
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
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "pay_model IN ('fixed', 'per_session', 'per_attendance')",
            name="ck_class_coaches_pay_model",
        ),
        sa.CheckConstraint(
            "pay_amount_cents >= 0",
            name="ck_class_coaches_pay_amount_nonneg",
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_class_coaches_range_valid",
        ),
    )

    # One (class, coach, role) link per tenant. A coach can be "ראשי" in
    # boxing only once; they CAN be "ראשי" AND "עוזר" in the same class
    # if the owner splits the pay structure that way.
    op.create_index(
        "ux_class_coaches_role",
        "class_coaches",
        ["class_id", "coach_id", "role"],
        unique=True,
    )
    op.create_index("ix_class_coaches_tenant", "class_coaches", ["tenant_id"])
    op.create_index("ix_class_coaches_class", "class_coaches", ["class_id"])
    op.create_index("ix_class_coaches_coach", "class_coaches", ["coach_id"])

    # ── 4. class_entries.coach_id ───────────────────────────────────
    # Nullable: backfill comes in a separate script, and a check-in that
    # can't find a matching coach still has to record. Earnings ignore
    # NULL-coach rows + emit a log event.
    op.add_column(
        "class_entries",
        sa.Column(
            "coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id", name="fk_entries_coach_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
    )
    # The earnings query is the only user of this index — filters out
    # undone + null-coach rows automatically.
    op.create_index(
        "ix_entries_coach_entered",
        "class_entries",
        ["coach_id", sa.text("entered_at DESC")],
        postgresql_where=sa.text("undone_at IS NULL AND coach_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_entries_coach_entered", table_name="class_entries")
    op.drop_constraint("fk_entries_coach_id", "class_entries", type_="foreignkey")
    op.drop_column("class_entries", "coach_id")

    op.drop_index("ix_class_coaches_coach", table_name="class_coaches")
    op.drop_index("ix_class_coaches_class", table_name="class_coaches")
    op.drop_index("ix_class_coaches_tenant", table_name="class_coaches")
    op.drop_index("ux_class_coaches_role", table_name="class_coaches")
    op.drop_table("class_coaches")

    op.drop_index("ix_coaches_tenant_status", table_name="coaches")
    op.drop_index("ux_coaches_user", table_name="coaches")
    op.drop_table("coaches")

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('super_admin', 'owner', 'staff', 'sales')",
    )
