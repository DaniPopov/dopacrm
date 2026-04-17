"""Pydantic domain entities for Subscription and SubscriptionEvent.

A Subscription is the commercial link between a Member and a Plan:
"Dana is on the Monthly Unlimited plan at 450 ILS/mo, paying cash,
expires 2026-05-01, currently active." Subscriptions own the lifecycle
(active / frozen / expired / cancelled / replaced) and the
price-lock-at-create-time snapshot.

Design notes (see docs/features/subscriptions.md for the full spec):

- ``cancelled`` is HARD-terminal (no transitions out; rejoin = new sub).
- ``expired`` is SOFT-terminal — ``renew()`` can bring it back to
  ``active`` on the same row, preserving tenure + the days_late telemetry
  the owner uses to judge member retention.
- ``replaced`` is terminal for the OLD sub only; it forwards via
  ``replaced_by_id`` to a new sub created during a plan change. Not
  counted as churn.
- The state-machine guards live as pure ``can_*`` methods here. The
  service calls them before mutating — keeps the rules out of SQL.

Cash vs card-auto (the expiry model):

- Cash / prepaid members: ``expires_at`` is set. Nightly job flips
  ``expires_at < today`` → ``expired``. Staff bumps ``expires_at``
  forward via ``/renew``.
- Card-auto members: ``expires_at = None``. Runs until manual cancel.

Freezing pauses paid time: on unfreeze (manual or the nightly auto-job),
``expires_at`` is pushed forward by the frozen duration. Industry standard.

SubscriptionEvent is the append-only timeline companion. One row per
state transition, written in the same transaction as the mutation.
Enables "who froze this sub?" and "how many members renewed late this
month?" queries without coupling analytics to mutable columns on the
Subscription row itself.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SubscriptionStatus(StrEnum):
    """Lifecycle status of a subscription."""

    ACTIVE = "active"
    FROZEN = "frozen"
    EXPIRED = "expired"  # SOFT-terminal — renew() can resurrect
    CANCELLED = "cancelled"  # HARD-terminal — rejoin = new sub
    REPLACED = "replaced"  # plan change — forwards via replaced_by_id


class SubscriptionEventType(StrEnum):
    """Discrete event types in the subscription timeline.

    Written into ``subscription_events`` inside the same transaction
    as the state change. ``created_by`` is None for system events
    (nightly expiry / auto-unfreeze jobs).
    """

    CREATED = "created"
    FROZEN = "frozen"
    UNFROZEN = "unfrozen"  # covers both manual and auto
    EXPIRED = "expired"
    RENEWED = "renewed"  # carries days_late in event_data
    REPLACED = "replaced"  # old sub's side of a plan change
    CHANGED_PLAN = "changed_plan"  # new sub's side of a plan change
    CANCELLED = "cancelled"  # carries optional reason/detail


class Subscription(BaseModel):
    """A member's subscription to a specific plan."""

    id: UUID
    tenant_id: UUID = Field(
        description="Gym this subscription belongs to. Scoping key on every read."
    )

    member_id: UUID
    plan_id: UUID

    status: SubscriptionStatus
    price_cents: int = Field(
        ge=0,
        description="Locked at create-time (or change-plan time) from plan.price_cents.",
    )
    currency: str = Field(
        description="Locked at create-time from plan.currency; immutable per sub."
    )

    started_at: date
    expires_at: date | None = Field(
        default=None,
        description=(
            "Cash / prepaid / one-time plans set this. Card-auto uses None "
            "(runs until cancelled). Nightly job flips expires_at < today → expired."
        ),
    )
    frozen_at: date | None = None
    frozen_until: date | None = Field(
        default=None,
        description="Optional auto-unfreeze date. None = open-ended freeze.",
    )
    expired_at: date | None = Field(
        default=None,
        description=(
            "Set when the sub flipped to expired. Preserved across renew so the "
            "owner's 'late renewals' report can compute days_late per event."
        ),
    )
    cancelled_at: date | None = None
    cancellation_reason: str | None = None
    replaced_at: date | None = None
    replaced_by_id: UUID | None = Field(
        default=None,
        description="FK to the new sub created by a plan change. Set iff status='replaced'.",
    )

    created_at: datetime
    updated_at: datetime

    # ── State-machine guards (pure, no I/O) ─────────────────────────────

    def can_freeze(self) -> bool:
        """Only active subs can be frozen."""
        return self.status == SubscriptionStatus.ACTIVE

    def can_unfreeze(self) -> bool:
        """Only frozen subs can be unfrozen."""
        return self.status == SubscriptionStatus.FROZEN

    def can_renew(self) -> bool:
        """Active (extend ahead) and expired (rescue) subs can be renewed.

        Cancelled subs CANNOT be renewed — the member actively said
        goodbye; rejoining is a new sub with a new started_at.
        """
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED)

    def can_change_plan(self) -> bool:
        """Only live subs can have their plan changed. Expired must renew first
        or start a new sub."""
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FROZEN)

    def can_cancel(self) -> bool:
        """Live and expired subs can be cancelled. Already-cancelled or replaced
        subs cannot — those are terminal."""
        return self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.FROZEN,
            SubscriptionStatus.EXPIRED,
        )

    def should_auto_unfreeze(self, today: date) -> bool:
        """True when the nightly job should flip this sub frozen → active.

        Only frozen subs with a ``frozen_until`` that has passed qualify.
        Open-ended freezes (``frozen_until is None``) require manual unfreeze.
        """
        return (
            self.status == SubscriptionStatus.FROZEN
            and self.frozen_until is not None
            and self.frozen_until <= today
        )

    def should_auto_expire(self, today: date) -> bool:
        """True when the nightly job should flip this sub active → expired.

        Only active subs with a past ``expires_at`` qualify. Card-auto
        subs (``expires_at is None``) never auto-expire.
        """
        return (
            self.status == SubscriptionStatus.ACTIVE
            and self.expires_at is not None
            and self.expires_at < today
        )

    def is_live(self) -> bool:
        """True iff this sub counts as the member's current sub.

        Mirrors the predicate on the DB's partial UNIQUE index.
        """
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FROZEN)

    def days_late(self, renewed_on: date) -> int:
        """For an expired-then-renewed sub, how many days past the original
        ``expired_at`` the renewal happened. 0 if not expired or not renewable.

        Used to populate the ``renewed`` event's ``event_data.days_late`` so
        the owner can see "5 members renewed 2+ days late this month".
        """
        if self.expired_at is None:
            return 0
        delta = (renewed_on - self.expired_at).days
        return max(0, delta)


class SubscriptionEvent(BaseModel):
    """Append-only timeline entry for a subscription.

    Written inside the same transaction as every state change on a
    ``Subscription``. Readers: the member-detail timeline UI, owner
    retention dashboards, and future audit exports.
    """

    id: UUID
    tenant_id: UUID
    subscription_id: UUID
    event_type: SubscriptionEventType
    event_data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form payload — days_late, frozen_until, reason, "
            "previous_plan_id, etc. JSONB on the DB side."
        ),
    )
    occurred_at: datetime
    created_by: UUID | None = Field(
        default=None,
        description="User who triggered the event. None = system (nightly job).",
    )
