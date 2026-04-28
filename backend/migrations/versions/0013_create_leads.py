"""create leads + lead_activities tables + leads feature flag backfill

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-27 10:00:00.000000

Two tables ship together because activities are append-only children of
leads and a single migration keeps the FK + cascade story atomic:

1. ``leads`` — pipeline records. Every gym walk-in / website inquiry /
   referral lives here until it converts into a Member or is marked
   lost. Status is the pipeline column (new, contacted, trial,
   converted, lost). ``converted_member_id`` is the FK that links a
   converted lead to its resulting Member row — set in the same
   transaction the convert endpoint opens.

2. ``lead_activities`` — append-only timeline of touchpoints (call,
   email, meeting, note) plus auto-generated ``status_change`` rows
   on every transition. No UPDATE / DELETE through the API.

3. ``tenants.features_enabled.leads`` backfill — existing rows get
   ``leads: false`` merged in. New tenants inherit ``{}`` from the
   server_default and ``is_feature_enabled`` returns False on missing
   key (fail-closed) so explicit backfill is only for forward-compat
   visibility in the super_admin Features UI.

See ``docs/features/leads.md`` for the full design + state machine +
convert transaction.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. leads ───────────────────────────────────────────────────────
    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_leads_tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'other'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_leads_assigned_to", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column(
            "converted_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "members.id",
                name="fk_leads_converted_member_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "custom_fields",
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
            "status IN ('new', 'contacted', 'trial', 'converted', 'lost')",
            name="ck_leads_status",
        ),
        sa.CheckConstraint(
            "source IN ('walk_in', 'website', 'referral', 'social_media', 'ad', 'other')",
            name="ck_leads_source",
        ),
        # When converted, the Member FK must be set. (No reverse — a
        # converted lead whose Member was deleted gets ``SET NULL`` from
        # the FK; that's an integrity edge that the service catches at
        # read time.)
        sa.CheckConstraint(
            "(status = 'converted') = (converted_member_id IS NOT NULL)",
            name="ck_leads_converted_consistency",
        ),
    )
    # Kanban bucketing + dashboard "leads in pipeline" widget.
    op.create_index(
        "ix_leads_tenant_status",
        "leads",
        ["tenant_id", "status"],
    )
    # Per-rep lookups (sales sees all today, but the column drives
    # reporting; index makes it cheap when the toggle ships).
    op.create_index(
        "ix_leads_tenant_assigned",
        "leads",
        ["tenant_id", "assigned_to"],
        postgresql_where=sa.text("assigned_to IS NOT NULL"),
    )
    # Default list ordering — newest first.
    op.create_index(
        "ix_leads_tenant_created",
        "leads",
        ["tenant_id", sa.text("created_at DESC")],
    )

    # ── 2. lead_activities ─────────────────────────────────────────────
    op.create_table(
        "lead_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # tenant_id denormalized — every query filters on it, and
        # joining lead_activities → leads to derive it for cross-tenant
        # probes is wasteful at scale.
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenants.id",
                name="fk_lead_activities_tenant_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "leads.id",
                name="fk_lead_activities_lead_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                name="fk_lead_activities_created_by",
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
        sa.CheckConstraint(
            "type IN ('call', 'email', 'note', 'meeting', 'status_change')",
            name="ck_lead_activities_type",
        ),
    )
    # Timeline query — the lead detail page's main read.
    op.create_index(
        "ix_lead_activities_lead_created",
        "lead_activities",
        ["lead_id", sa.text("created_at DESC")],
    )
    # "What did the team do today?" report (future).
    op.create_index(
        "ix_lead_activities_tenant_created",
        "lead_activities",
        ["tenant_id", sa.text("created_at DESC")],
    )

    # ── 3. tenants.features_enabled.leads = false backfill ─────────────
    # JSONB merge — existing rows keep their other flags, gain leads=false.
    # New tenants inherit ``{}`` from the server_default; the backend's
    # ``is_feature_enabled`` returns False on missing key (fail-closed),
    # so this backfill is mainly for visibility in the super_admin UI.
    op.execute(
        "UPDATE tenants "
        "SET features_enabled = features_enabled || '{\"leads\": false}'::jsonb"
    )


def downgrade() -> None:
    op.drop_index("ix_lead_activities_tenant_created", table_name="lead_activities")
    op.drop_index("ix_lead_activities_lead_created", table_name="lead_activities")
    op.drop_table("lead_activities")

    op.drop_index("ix_leads_tenant_created", table_name="leads")
    op.drop_index("ix_leads_tenant_assigned", table_name="leads")
    op.drop_index("ix_leads_tenant_status", table_name="leads")
    op.drop_table("leads")

    # Strip the leads key from existing tenants. Other flags preserved.
    op.execute("UPDATE tenants SET features_enabled = features_enabled - 'leads'")
