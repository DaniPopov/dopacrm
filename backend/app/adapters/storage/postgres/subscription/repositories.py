"""Repository for ``subscriptions`` + ``subscription_events``.

Two entities, one repo — they're always written together (every state
change on a subscription writes an event in the same transaction).

Mutation style: every state transition uses bulk ``UPDATE`` via
``sqlalchemy.update()`` (not ORM attribute mutation on a fetched row).
This matches the pattern used by MemberRepository and
MembershipPlanRepository, and avoids an async-specific gotcha — after an
ORM-level mutation + flush, SQLAlchemy marks ``onupdate=func.now()``
columns as expired and tries to refresh them synchronously on next
access, which raises ``MissingGreenlet`` in async context. Bulk UPDATE
skips the identity-map refresh entirely; we re-fetch domain objects
with a fresh SELECT after flush.

Tenant-scoping is the SERVICE's job. This repo trusts the service to
pass the right tenant_id and to validate state-machine transitions
before calling these methods. The repo's responsibilities are:

1. Raw CRUD against the ORM (create, find, list).
2. Atomic state transitions that touch BOTH the sub row AND an event
   row in the same flush.
3. Nightly-job queries (``find_due_for_unfreeze`` /
   ``find_due_for_expire``) that hit the partial indexes.

The service never calls ``_session.commit`` — that's api-layer wiring.
The repo only flushes. If a caller (the Celery beat task) wants to
batch many transitions, it commits at the end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, asc, desc, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.storage.postgres.subscription.models import (
    SubscriptionEventORM,
    SubscriptionORM,
)
from app.domain.entities.subscription import (
    PaymentMethod,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)
from app.domain.exceptions import (
    MemberAlreadyHasActiveSubscriptionError,
    SubscriptionNotFoundError,
)

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


# Sentinel for "caller didn't pass this argument" on renew — lets us
# distinguish "leave detail alone" (the default) from "explicitly clear
# detail" (None). A plain `None` default can't do both.
_UNSET: Any = object()


# ── domain↔ORM mapping ──────────────────────────────────────────────────────


def _sub_to_domain(orm: SubscriptionORM) -> Subscription:
    return Subscription(
        id=orm.id,
        tenant_id=orm.tenant_id,
        member_id=orm.member_id,
        plan_id=orm.plan_id,
        status=SubscriptionStatus(orm.status),
        price_cents=orm.price_cents,
        currency=orm.currency,
        payment_method=PaymentMethod(orm.payment_method),
        payment_method_detail=orm.payment_method_detail,
        started_at=orm.started_at,
        expires_at=orm.expires_at,
        frozen_at=orm.frozen_at,
        frozen_until=orm.frozen_until,
        expired_at=orm.expired_at,
        cancelled_at=orm.cancelled_at,
        cancellation_reason=orm.cancellation_reason,
        replaced_at=orm.replaced_at,
        replaced_by_id=orm.replaced_by_id,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _event_to_domain(orm: SubscriptionEventORM) -> SubscriptionEvent:
    return SubscriptionEvent(
        id=orm.id,
        tenant_id=orm.tenant_id,
        subscription_id=orm.subscription_id,
        event_type=SubscriptionEventType(orm.event_type),
        event_data=dict(orm.event_data or {}),
        occurred_at=orm.occurred_at,
        created_by=orm.created_by,
    )


# ── repository ─────────────────────────────────────────────────────────────


class SubscriptionRepository:
    """CRUD + timeline-writes for subscriptions. No transactions owned."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ──────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: UUID,
        member_id: UUID,
        plan_id: UUID,
        price_cents: int,
        currency: str,
        started_at: date,
        expires_at: date | None,
        created_by: UUID | None,
        payment_method: PaymentMethod = PaymentMethod.CASH,
        payment_method_detail: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> Subscription:
        """Insert a new ACTIVE subscription + its 'created' event.

        Raises:
            MemberAlreadyHasActiveSubscriptionError: partial-UNIQUE rejected
                a second live sub for the same member (service should have
                caught this first for a cleaner message, but this is the
                last line of defense).
        """
        orm = SubscriptionORM(
            tenant_id=tenant_id,
            member_id=member_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE.value,
            price_cents=price_cents,
            currency=currency,
            payment_method=payment_method.value,
            payment_method_detail=payment_method_detail,
            started_at=started_at,
            expires_at=expires_at,
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise MemberAlreadyHasActiveSubscriptionError(str(member_id)) from exc

        new_id = orm.id
        self._session.add(
            SubscriptionEventORM(
                tenant_id=tenant_id,
                subscription_id=new_id,
                event_type=SubscriptionEventType.CREATED.value,
                event_data=event_data or {},
                created_by=created_by,
            )
        )
        await self._session.flush()

        # Re-fetch so server-populated columns (created_at/updated_at) are
        # loaded via the current async connection. See module docstring.
        refreshed = await self.find_by_id(new_id)
        assert refreshed is not None  # we just inserted it
        return refreshed

    # ── Read ───────────────────────────────────────────────────────────

    async def find_by_id(self, sub_id: UUID) -> Subscription | None:
        """Primary-key lookup. Tenant scoping is the service's job."""
        result = await self._session.execute(
            select(SubscriptionORM).where(SubscriptionORM.id == sub_id)
        )
        orm = result.scalar_one_or_none()
        return _sub_to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        member_id: UUID | None = None,
        status: SubscriptionStatus | None = None,
        plan_id: UUID | None = None,
        expires_before: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Subscription]:
        """List subs in one tenant, filtered. Newest first."""
        stmt = select(SubscriptionORM).where(SubscriptionORM.tenant_id == tenant_id)
        if member_id is not None:
            stmt = stmt.where(SubscriptionORM.member_id == member_id)
        if status is not None:
            stmt = stmt.where(SubscriptionORM.status == status.value)
        if plan_id is not None:
            stmt = stmt.where(SubscriptionORM.plan_id == plan_id)
        if expires_before is not None:
            stmt = stmt.where(
                and_(
                    SubscriptionORM.expires_at.is_not(None),
                    SubscriptionORM.expires_at < expires_before,
                )
            )
        stmt = stmt.order_by(desc(SubscriptionORM.created_at)).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_sub_to_domain(orm) for orm in result.scalars()]

    async def list_for_member(self, tenant_id: UUID, member_id: UUID) -> list[Subscription]:
        """Full history for one member, newest first."""
        result = await self._session.execute(
            select(SubscriptionORM)
            .where(
                SubscriptionORM.tenant_id == tenant_id,
                SubscriptionORM.member_id == member_id,
            )
            .order_by(desc(SubscriptionORM.created_at))
        )
        return [_sub_to_domain(orm) for orm in result.scalars()]

    async def find_live_for_member(self, tenant_id: UUID, member_id: UUID) -> Subscription | None:
        """Return the member's live sub (active or frozen), if any.

        Matches the partial-UNIQUE predicate — at most one row qualifies.
        """
        result = await self._session.execute(
            select(SubscriptionORM).where(
                SubscriptionORM.tenant_id == tenant_id,
                SubscriptionORM.member_id == member_id,
                SubscriptionORM.status.in_(
                    [
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.FROZEN.value,
                    ]
                ),
            )
        )
        orm = result.scalar_one_or_none()
        return _sub_to_domain(orm) if orm else None

    # ── Event timeline reads ───────────────────────────────────────────

    async def list_events(self, sub_id: UUID) -> list[SubscriptionEvent]:
        """Event timeline for a single sub, newest first."""
        result = await self._session.execute(
            select(SubscriptionEventORM)
            .where(SubscriptionEventORM.subscription_id == sub_id)
            .order_by(desc(SubscriptionEventORM.occurred_at))
        )
        return [_event_to_domain(orm) for orm in result.scalars()]

    # ── Nightly-job queries (hit the partial indexes) ─────────────────

    async def find_due_for_unfreeze(self, *, today: date) -> list[Subscription]:
        """Frozen subs whose frozen_until has arrived/passed."""
        result = await self._session.execute(
            select(SubscriptionORM)
            .where(
                SubscriptionORM.status == SubscriptionStatus.FROZEN.value,
                SubscriptionORM.frozen_until.is_not(None),
                SubscriptionORM.frozen_until <= today,
            )
            .order_by(asc(SubscriptionORM.frozen_until))
        )
        return [_sub_to_domain(orm) for orm in result.scalars()]

    async def find_due_for_expire(self, *, today: date) -> list[Subscription]:
        """Active subs whose expires_at is in the past."""
        result = await self._session.execute(
            select(SubscriptionORM)
            .where(
                SubscriptionORM.status == SubscriptionStatus.ACTIVE.value,
                SubscriptionORM.expires_at.is_not(None),
                SubscriptionORM.expires_at < today,
            )
            .order_by(asc(SubscriptionORM.expires_at))
        )
        return [_sub_to_domain(orm) for orm in result.scalars()]

    # ── State transitions ─────────────────────────────────────────────
    # Each transition: bulk UPDATE the sub row + INSERT an event, both
    # in the same flush. We re-fetch the sub to return a fresh domain
    # entity (server-populated updated_at is on the refreshed row).

    async def _require_sub(self, sub_id: UUID) -> Subscription:
        """Load a sub or raise. Used by transitions to verify existence +
        get tenant_id for the event row."""
        sub = await self.find_by_id(sub_id)
        if sub is None:
            raise SubscriptionNotFoundError(str(sub_id))
        return sub

    def _add_event(
        self,
        *,
        tenant_id: UUID,
        sub_id: UUID,
        event_type: SubscriptionEventType,
        created_by: UUID | None,
        event_data: dict[str, Any] | None = None,
    ) -> None:
        """Stage an event row. Flushed by the caller."""
        self._session.add(
            SubscriptionEventORM(
                tenant_id=tenant_id,
                subscription_id=sub_id,
                event_type=event_type.value,
                event_data=event_data or {},
                created_by=created_by,
            )
        )

    async def freeze(
        self,
        sub_id: UUID,
        *,
        frozen_at: date,
        frozen_until: date | None,
        created_by: UUID | None,
    ) -> Subscription:
        existing = await self._require_sub(sub_id)
        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(
                status=SubscriptionStatus.FROZEN.value,
                frozen_at=frozen_at,
                frozen_until=frozen_until,
            )
        )
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.FROZEN,
            created_by=created_by,
            event_data={"frozen_until": frozen_until.isoformat() if frozen_until else None},
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def unfreeze(
        self,
        sub_id: UUID,
        *,
        today: date,
        new_expires_at: date | None,
        created_by: UUID | None,
        auto: bool = False,
    ) -> Subscription:
        """Unfreeze. ``new_expires_at`` is the freeze-extended expiry (service
        computes it) or None for card-auto subs. ``auto=True`` marks it as a
        system event in the log."""
        existing = await self._require_sub(sub_id)
        frozen_days: int | None = None
        if existing.frozen_at is not None:
            frozen_days = (today - existing.frozen_at).days

        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(
                status=SubscriptionStatus.ACTIVE.value,
                frozen_at=None,
                frozen_until=None,
                expires_at=new_expires_at,
            )
        )
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.UNFROZEN,
            created_by=None if auto else created_by,
            event_data={
                "auto": auto,
                "frozen_days": frozen_days,
                "new_expires_at": new_expires_at.isoformat() if new_expires_at else None,
            },
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def expire(self, sub_id: UUID, *, today: date) -> Subscription:
        """Flip an active sub to expired. System event (nightly job)."""
        existing = await self._require_sub(sub_id)
        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(
                status=SubscriptionStatus.EXPIRED.value,
                expired_at=today,
            )
        )
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.EXPIRED,
            created_by=None,
            event_data={"expired_on": today.isoformat()},
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def renew(
        self,
        sub_id: UUID,
        *,
        new_expires_at: date,
        days_late: int,
        created_by: UUID | None,
        new_payment_method: PaymentMethod | None = None,
        new_payment_method_detail: Any = _UNSET,
    ) -> Subscription:
        """Push expires_at forward. Resurrects expired → active. Keeps
        started_at, price_cents, plan_id, currency — the row's identity
        is preserved on renewal. ``expired_at`` stays as a historical marker.

        Optionally updates payment_method too — a member moving from cash
        to standing order typically does so at renewal time. Pass
        ``new_payment_method_detail=_unset`` (the default) to leave detail
        alone; pass ``None`` to explicitly clear it; pass a string to set.
        """
        existing = await self._require_sub(sub_id)
        previous_expires_at = existing.expires_at
        previous_method = existing.payment_method

        values: dict[str, Any] = {
            "status": SubscriptionStatus.ACTIVE.value,
            "expires_at": new_expires_at,
            # expired_at stays; do not reset.
        }
        if new_payment_method is not None:
            values["payment_method"] = new_payment_method.value
        if new_payment_method_detail is not _UNSET:
            values["payment_method_detail"] = new_payment_method_detail

        await self._session.execute(
            update(SubscriptionORM).where(SubscriptionORM.id == sub_id).values(**values)
        )

        event_data: dict[str, Any] = {
            "days_late": days_late,
            "previous_expires_at": previous_expires_at.isoformat() if previous_expires_at else None,
            "new_expires_at": new_expires_at.isoformat(),
        }
        if new_payment_method is not None and new_payment_method != previous_method:
            event_data["previous_payment_method"] = previous_method.value
            event_data["new_payment_method"] = new_payment_method.value

        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.RENEWED,
            created_by=created_by,
            event_data=event_data,
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def mark_replaced_pending(
        self,
        sub_id: UUID,
        *,
        replaced_at: date,
        created_by: UUID | None,
        event_data: dict[str, Any] | None = None,
    ) -> Subscription:
        """Phase 1 of plan change: flip the OLD sub to ``replaced`` with
        ``replaced_by_id=NULL`` (to be set in phase 2 once the new sub's
        id is known). This step clears the old sub from the partial-UNIQUE
        live-set so the new sub can insert without violating the "one
        live sub per member" invariant.

        The service pairs this with ``set_replaced_by`` inside the same
        transaction; if the transaction is rolled back, the old sub is
        restored. If the transaction commits without the second step,
        we'd have a committed row violating the service-level invariant
        "replaced subs always point to their successor" — the service
        is expected to always pair these two calls.
        """
        existing = await self._require_sub(sub_id)
        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(
                status=SubscriptionStatus.REPLACED.value,
                replaced_at=replaced_at,
                replaced_by_id=None,
            )
        )
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.REPLACED,
            created_by=created_by,
            event_data=event_data or {},
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def set_replaced_by(self, sub_id: UUID, *, replaced_by_id: UUID) -> Subscription:
        """Phase 2 of plan change: fill in the forward link once the new
        sub exists. No event — ``mark_replaced_pending`` already logged
        the REPLACED event."""
        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(replaced_by_id=replaced_by_id)
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed

    async def write_changed_plan_event(
        self,
        sub_id: UUID,
        *,
        from_sub_id: UUID,
        from_plan_id: UUID,
        created_by: UUID | None,
    ) -> None:
        """Companion event for the NEW sub in a plan-change transaction.

        The new sub's 'created' event is written by ``create()``; this
        adds a second event so the new sub's timeline starts with BOTH
        'created' + 'changed_plan' (the latter explaining the context).
        """
        existing = await self._require_sub(sub_id)
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.CHANGED_PLAN,
            created_by=created_by,
            event_data={
                "from_subscription_id": str(from_sub_id),
                "from_plan_id": str(from_plan_id),
            },
        )
        await self._session.flush()

    async def cancel(
        self,
        sub_id: UUID,
        *,
        cancelled_at: date,
        reason: str | None,
        detail: str | None,
        created_by: UUID | None,
    ) -> Subscription:
        """Hard-terminal. Reason (canonical dropdown key) + optional detail
        go into event_data for churn analytics."""
        existing = await self._require_sub(sub_id)
        await self._session.execute(
            update(SubscriptionORM)
            .where(SubscriptionORM.id == sub_id)
            .values(
                status=SubscriptionStatus.CANCELLED.value,
                cancelled_at=cancelled_at,
                cancellation_reason=reason,
            )
        )
        self._add_event(
            tenant_id=existing.tenant_id,
            sub_id=sub_id,
            event_type=SubscriptionEventType.CANCELLED,
            created_by=created_by,
            event_data={"reason": reason, "detail": detail},
        )
        await self._session.flush()
        refreshed = await self.find_by_id(sub_id)
        assert refreshed is not None
        return refreshed
