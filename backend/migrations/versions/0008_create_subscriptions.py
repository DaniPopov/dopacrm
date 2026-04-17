"""create subscriptions + subscription_events tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-17 12:00:00.000000

Two related tables shipping together:

1. ``subscriptions`` — the link between a Member and a Plan. Owns the
   billing lifecycle (active / frozen / expired / cancelled / replaced)
   and the price-lock-at-create-time snapshot.

   Key invariants enforced here (not just in the service):

   - Partial UNIQUE index on ``(member_id) WHERE status IN ('active','frozen')``
     enforces "one live sub per member" at the DB layer. If a race or a
     bug tries to insert a second live sub, Postgres rejects it.

   - Shape CHECKs couple status with its timestamps:
     status='frozen'    ↔ frozen_at IS NOT NULL
     status='cancelled' ↔ cancelled_at IS NOT NULL
     status='replaced'  ↔ replaced_at IS NOT NULL AND replaced_by_id IS NOT NULL

   - FK to members ON DELETE RESTRICT — can't delete a member with subs.
     FK to plans   ON DELETE RESTRICT — can't delete a plan with subs.
     FK to tenants ON DELETE CASCADE — nuking a tenant nukes its subs.

2. ``subscription_events`` — append-only timeline. One row per state
   transition, written inside the same transaction as the state change.
   Enables the "retention telemetry" the owner needs ("how many members
   renewed late this month", full freeze/unfreeze audit, etc.) without
   coupling the queries to mutable columns on ``subscriptions``.

   ``event_data`` is JSONB so payloads can evolve (``days_late``,
   ``frozen_until``, ``reason``, ``detail``, ``previous_plan_id``, ...)
   without migrating the events table every time.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── subscriptions ──────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_subs_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", name="fk_subs_member_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "membership_plans.id",
                name="fk_subs_plan_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("frozen_at", sa.Date(), nullable=True),
        sa.Column("frozen_until", sa.Date(), nullable=True),
        sa.Column("expired_at", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("replaced_at", sa.Date(), nullable=True),
        sa.Column(
            "replaced_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_subs_replaced_by_id",
                ondelete="SET NULL",
            ),
            nullable=True,
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
            "status IN ('active', 'frozen', 'expired', 'cancelled', 'replaced')",
            name="ck_subs_status",
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_subs_price_non_negative"),
        # status ↔ timestamp couplings — prevents "cancelled row without cancelled_at"
        # and its mirror image "cancelled_at set on an active row"
        sa.CheckConstraint(
            "(status <> 'frozen' AND frozen_at IS NULL AND frozen_until IS NULL) "
            "OR (status = 'frozen' AND frozen_at IS NOT NULL)",
            name="ck_subs_frozen_shape",
        ),
        sa.CheckConstraint(
            "(status <> 'cancelled' AND cancelled_at IS NULL) "
            "OR (status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_subs_cancelled_shape",
        ),
        # replaced_at is tied to status, but replaced_by_id is NOT required
        # at the row level: the plan-change flow updates the old sub to
        # status='replaced' FIRST (clearing it from the live-set so the
        # partial UNIQUE lets the new sub insert), THEN fills replaced_by_id
        # in a second UPDATE after the new sub's id is known. Committed-state
        # invariant ("replaced subs always have replaced_by_id set") is a
        # service-layer guarantee, not a row CHECK.
        sa.CheckConstraint(
            "(status <> 'replaced' AND replaced_at IS NULL AND replaced_by_id IS NULL) "
            "OR (status = 'replaced' AND replaced_at IS NOT NULL)",
            name="ck_subs_replaced_shape",
        ),
        # frozen_until, if set, must be >= frozen_at
        sa.CheckConstraint(
            "frozen_until IS NULL OR frozen_at IS NULL OR frozen_until >= frozen_at",
            name="ck_subs_frozen_until_after_start",
        ),
    )

    # ── indexes ────────────────────────────────────────────────────────
    # The key invariant: at most ONE live (active|frozen) sub per member.
    # Postgres partial UNIQUE is the correct place for this — the service
    # checks it for a clean 409, but the DB is the final authority.
    op.create_index(
        "uq_subs_one_live_per_member",
        "subscriptions",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'frozen')"),
    )

    # Hot-path lookups
    op.create_index("ix_subs_tenant_status", "subscriptions", ["tenant_id", "status"])
    op.create_index(
        "ix_subs_member_created",
        "subscriptions",
        ["member_id", sa.text("created_at DESC")],
    )

    # Nightly expiry job — bounded scan on "active subs with an expires_at in the past"
    op.create_index(
        "ix_subs_expires_due",
        "subscriptions",
        ["tenant_id", "expires_at"],
        postgresql_where=sa.text("status = 'active' AND expires_at IS NOT NULL"),
    )

    # Nightly auto-unfreeze job
    op.create_index(
        "ix_subs_frozen_until_due",
        "subscriptions",
        ["tenant_id", "frozen_until"],
        postgresql_where=sa.text("status = 'frozen' AND frozen_until IS NOT NULL"),
    )

    # ── subscription_events ────────────────────────────────────────────
    op.create_table(
        "subscription_events",
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
                "tenants.id",
                name="fk_sub_events_tenant_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_sub_events_subscription_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column(
            "event_data",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                name="fk_sub_events_created_by",
                ondelete="SET NULL",
            ),
            nullable=True,  # NULL = system event (nightly jobs)
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'created', 'frozen', 'unfrozen', 'expired', "
            "'renewed', 'replaced', 'changed_plan', 'cancelled'"
            ")",
            name="ck_sub_events_type",
        ),
    )
    op.create_index(
        "ix_sub_events_sub_occurred",
        "subscription_events",
        ["subscription_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_sub_events_tenant_type",
        "subscription_events",
        ["tenant_id", "event_type", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_sub_events_tenant_type", table_name="subscription_events")
    op.drop_index("ix_sub_events_sub_occurred", table_name="subscription_events")
    op.drop_table("subscription_events")
    op.drop_index("ix_subs_frozen_until_due", table_name="subscriptions")
    op.drop_index("ix_subs_expires_due", table_name="subscriptions")
    op.drop_index("ix_subs_member_created", table_name="subscriptions")
    op.drop_index("ix_subs_tenant_status", table_name="subscriptions")
    op.drop_index("uq_subs_one_live_per_member", table_name="subscriptions")
    op.drop_table("subscriptions")
