"""create schedule tables + tenant feature flags

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-24 16:00:00.000000

Three DB changes ship together because they're interlocked:

1. ``tenants.features_enabled`` JSONB — per-tenant on/off switch for
   gated features. See ``docs/features/feature-flags.md``. Default
   empty ``{}`` for new tenants (gated features OFF). Existing
   tenants backfilled with ``{"coaches": true}`` so their live
   Coaches feature keeps working.

2. ``class_schedule_templates`` — recurring rules. Owner creates
   once; the service materializes sessions from them. Editing a
   template triggers re-materialization of future non-customized
   sessions.

3. ``class_sessions`` — concrete materialized occurrences. Calendar
   view queries against this table. Individual edits (cancel, swap
   coach, shift time) set ``is_customized=TRUE`` so template
   re-materialization doesn't stomp owner choices.

4. ``class_entries.session_id`` — nullable FK for the attendance
   attribution upgrade. Set server-side at check-in when a scheduled
   session overlaps ``entered_at``. Historical rows stay NULL — no
   retroactive attribution.

See ``docs/features/schedule.md`` for the full design + materialization
math + attribution rules.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. tenants.features_enabled + backfill ─────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "features_enabled",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Backfill existing tenants with coaches=true so the live Coaches
    # feature keeps working for gyms already using it.
    op.execute(
        "UPDATE tenants SET features_enabled = '{\"coaches\": true}'::jsonb"
    )

    # ── 2. class_schedule_templates ────────────────────────────────
    op.create_table(
        "class_schedule_templates",
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
                "tenants.id", name="fk_sched_templates_tenant_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "classes.id", name="fk_sched_templates_class_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        # Which weekdays the template runs. Sunday-indexed 3-letter codes.
        sa.Column(
            "weekdays",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        # Time-of-day boundaries. Date is supplied per materialized session.
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        # Default coach assignment per materialized session.
        sa.Column(
            "head_coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id",
                name="fk_sched_templates_head_coach_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "assistant_coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id",
                name="fk_sched_templates_assistant_coach_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "starts_on",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("ends_on", sa.Date(), nullable=True),
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
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "cardinality(weekdays) > 0", name="ck_sched_templates_weekdays_nonempty"
        ),
        sa.CheckConstraint(
            "end_time > start_time", name="ck_sched_templates_time_order"
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="ck_sched_templates_range_valid",
        ),
    )
    op.create_index(
        "ix_sched_templates_tenant_class",
        "class_schedule_templates",
        ["tenant_id", "class_id"],
    )
    op.create_index(
        "ix_sched_templates_active",
        "class_schedule_templates",
        ["tenant_id"],
        postgresql_where=sa.text("is_active"),
    )

    # ── 3. class_sessions ──────────────────────────────────────────
    op.create_table(
        "class_sessions",
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
                "tenants.id", name="fk_sessions_tenant_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "classes.id", name="fk_sessions_class_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        # Back-pointer to the template. NULL = ad-hoc session.
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "class_schedule_templates.id",
                name="fk_sessions_template_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "head_coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id",
                name="fk_sessions_head_coach_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "assistant_coach_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "coaches.id",
                name="fk_sessions_assistant_coach_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column(
            "is_customized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", name="fk_sessions_cancelled_by", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "status IN ('scheduled', 'cancelled')", name="ck_sessions_status"
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name="ck_sessions_time_order"
        ),
        # Shape: cancelled iff cancelled_at is set.
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_sessions_cancelled_shape",
        ),
    )

    # Calendar queries: "sessions this week for this tenant."
    op.create_index(
        "ix_sessions_tenant_range",
        "class_sessions",
        ["tenant_id", "starts_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    # Attribution lookup: "which session is running for this class around now?"
    op.create_index(
        "ix_sessions_class_starts",
        "class_sessions",
        ["class_id", "starts_at", "status"],
    )
    # Per-coach weekly view + earnings scan.
    op.create_index(
        "ix_sessions_head_coach",
        "class_sessions",
        ["head_coach_id", "starts_at"],
        postgresql_where=sa.text(
            "status = 'scheduled' AND head_coach_id IS NOT NULL"
        ),
    )
    # Materialization idempotency: one session per (template, starts_at).
    # Partial so ad-hoc sessions (template_id IS NULL) aren't constrained.
    op.create_index(
        "ux_sessions_template_starts",
        "class_sessions",
        ["template_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("template_id IS NOT NULL"),
    )

    # ── 4. class_entries.session_id ────────────────────────────────
    op.add_column(
        "class_entries",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "class_sessions.id",
                name="fk_entries_session_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    # The earnings + owner-audit queries on session-attributed entries.
    op.create_index(
        "ix_entries_session",
        "class_entries",
        ["session_id", sa.text("entered_at DESC")],
        postgresql_where=sa.text(
            "undone_at IS NULL AND session_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_entries_session", table_name="class_entries")
    op.drop_constraint("fk_entries_session_id", "class_entries", type_="foreignkey")
    op.drop_column("class_entries", "session_id")

    op.drop_index("ux_sessions_template_starts", table_name="class_sessions")
    op.drop_index("ix_sessions_head_coach", table_name="class_sessions")
    op.drop_index("ix_sessions_class_starts", table_name="class_sessions")
    op.drop_index("ix_sessions_tenant_range", table_name="class_sessions")
    op.drop_table("class_sessions")

    op.drop_index("ix_sched_templates_active", table_name="class_schedule_templates")
    op.drop_index(
        "ix_sched_templates_tenant_class", table_name="class_schedule_templates"
    )
    op.drop_table("class_schedule_templates")

    op.drop_column("tenants", "features_enabled")
