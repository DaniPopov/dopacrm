"""Subscription service — orchestrates the commercial lifecycle.

Layer 2. Home of every business rule that makes Subscriptions work the
way a gym actually operates:

- **Tenant scoping** on every read + mutation. super_admin is permitted
  to read (platform support) but NOT to mutate — commercial actions
  belong to the gym.
- **Role gates.** Every mutation is staff+ (staff, owner, super_admin).
  Daily operations must not be blocked on owner attention.
- **Price lock.** Both ``create`` and ``change_plan`` snapshot the plan's
  current ``price_cents`` + ``currency`` onto the new sub. Callers cannot
  override — the API schema doesn't expose a price field.
- **Plan active check.** New subs (create + change_plan) require an
  active plan. Deactivating a plan doesn't affect existing subs.
- **Plan tenant match.** Redundant with the FK, but surfaces a useful
  typed error instead of a generic IntegrityError.
- **One-live-sub invariant.** Service-level pre-check for a clean 409;
  the DB partial UNIQUE is the last line of defense.
- **State-machine guards** via the entity's ``can_*`` methods.
- **Freeze extends expires_at.** Industry standard — paused time doesn't
  eat paid time. When ``unfreeze`` runs (manual OR the nightly job),
  expires_at is pushed forward by the frozen duration.
- **Renew math.** Default extension = the plan's billing period
  (monthly=30d / quarterly=90d / yearly=365d / one_time=duration_days).
  Caller can override with an explicit ``new_expires_at``. On
  ``expired → active`` renewals, ``days_late`` is computed and logged.
- **Plan change** (upgrade / downgrade) uses the repo's two-phase
  flow: mark old sub ``replaced`` (clears it from the live-set),
  insert new sub (fresh price snapshot), then link the old sub forward.
  All in one transaction.
- **Member.status sync.** Every subscription state change bumps
  members.status in the same transaction so the member list + dashboard
  show the right badge.

Everything commits at the end of the method, matching the other
services. Caller (API handler) doesn't wrap in its own transaction.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING
from uuid import UUID as _UUID

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.domain.entities.member import MemberStatus
from app.domain.entities.membership_plan import BillingPeriod, PlanType
from app.domain.entities.subscription import (
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from app.domain.entities.user import Role
from app.domain.exceptions import (
    InsufficientPermissionsError,
    InvalidSubscriptionStateTransitionError,
    MemberAlreadyHasActiveSubscriptionError,
    MembershipPlanNotFoundError,
    SamePlanChangeError,
    SubscriptionNotFoundError,
    SubscriptionPlanMismatchError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload


# Default extension days per billing period. One-time uses plan.duration_days.
_BILLING_PERIOD_DAYS = {
    BillingPeriod.MONTHLY: 30,
    BillingPeriod.QUARTERLY: 90,
    BillingPeriod.YEARLY: 365,
}


class SubscriptionService:
    """Subscriptions lifecycle orchestrator."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SubscriptionRepository(session)
        self._plan_repo = MembershipPlanRepository(session)
        self._member_repo = MemberRepository(session)

    # ── Commands ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
        plan_id: UUID,
        started_at: date | None = None,
        expires_at: date | None = None,
    ) -> Subscription:
        """Enroll a member in a plan.

        - ``started_at`` defaults to today. Future dates are allowed.
        - ``expires_at`` is the caller's call:
            - cash / prepaid → set to the next payment due date
            - card-auto → leave None ("runs until cancelled")
            - one-time plan + caller omits → auto-set to started_at + duration_days
        - Price + currency snapshot comes from ``plan`` at create time.
        - Fails 409 if the member already has a live (active/frozen) sub.
        """
        tenant_id = self._require_staff_in_tenant(caller)
        caller_id = self._caller_uuid(caller)

        plan = await self._plan_repo.find_by_id(plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(str(plan_id))
        if str(plan.tenant_id) != str(tenant_id):
            raise SubscriptionPlanMismatchError()
        if not plan.is_active:
            raise InvalidSubscriptionStateTransitionError(current="inactive", action="subscribe to")

        # Member must exist in the same tenant (belt-and-suspenders; the
        # live-sub check below also implicitly requires an existing member
        # via the partial UNIQUE index).
        member = await self._member_repo.find_by_id(member_id)
        if member is None or str(member.tenant_id) != str(tenant_id):
            raise SubscriptionPlanMismatchError()

        # Pre-check the "one live sub per member" invariant for a clean 409.
        existing_live = await self._repo.find_live_for_member(tenant_id, member_id)
        if existing_live is not None:
            raise MemberAlreadyHasActiveSubscriptionError(str(member_id))

        resolved_start = started_at or date.today()
        resolved_expires = self._resolve_expires_at(
            plan=plan, started_at=resolved_start, caller_override=expires_at
        )

        sub = await self._repo.create(
            tenant_id=tenant_id,
            member_id=member_id,
            plan_id=plan_id,
            price_cents=plan.price_cents,
            currency=plan.currency,
            started_at=resolved_start,
            expires_at=resolved_expires,
            created_by=caller_id,
            event_data={"plan_id": str(plan_id)},
        )

        # Sync member.status to active (they may have been expired / cancelled).
        await self._sync_member_status(member_id, MemberStatus.ACTIVE)
        await self._session.commit()
        return sub

    async def freeze(
        self,
        *,
        caller: TokenPayload,
        sub_id: UUID,
        frozen_until: date | None = None,
    ) -> Subscription:
        """Pause the sub. Optional ``frozen_until`` for an auto-unfreeze date."""
        sub, caller_id = await self._prepare_transition(caller, sub_id)
        if not sub.can_freeze():
            raise InvalidSubscriptionStateTransitionError(current=sub.status.value, action="freeze")

        updated = await self._repo.freeze(
            sub_id,
            frozen_at=date.today(),
            frozen_until=frozen_until,
            created_by=caller_id,
        )
        await self._sync_member_status(sub.member_id, MemberStatus.FROZEN)
        await self._session.commit()
        return updated

    async def unfreeze(
        self,
        *,
        caller: TokenPayload,
        sub_id: UUID,
    ) -> Subscription:
        """Resume a frozen sub manually. Extends expires_at by the frozen duration."""
        sub, caller_id = await self._prepare_transition(caller, sub_id)
        if not sub.can_unfreeze():
            raise InvalidSubscriptionStateTransitionError(
                current=sub.status.value, action="unfreeze"
            )
        today = date.today()
        new_expires_at = self._extend_expires_for_unfreeze(sub, today=today)

        updated = await self._repo.unfreeze(
            sub_id,
            today=today,
            new_expires_at=new_expires_at,
            created_by=caller_id,
            auto=False,
        )
        await self._sync_member_status(sub.member_id, MemberStatus.ACTIVE)
        await self._session.commit()
        return updated

    async def renew(
        self,
        *,
        caller: TokenPayload,
        sub_id: UUID,
        new_expires_at: date | None = None,
    ) -> Subscription:
        """Push expires_at forward. Works on ``active`` (extend-ahead) and
        ``expired`` (rescue). On expired→active, preserves the row's identity
        (same started_at, price, plan) and logs ``days_late``."""
        sub, caller_id = await self._prepare_transition(caller, sub_id)
        if not sub.can_renew():
            raise InvalidSubscriptionStateTransitionError(current=sub.status.value, action="renew")

        plan = await self._plan_repo.find_by_id(sub.plan_id)
        if plan is None:
            # Shouldn't happen — FK RESTRICT prevents plan deletion. Defensive.
            raise MembershipPlanNotFoundError(str(sub.plan_id))

        today = date.today()
        resolved = new_expires_at or self._default_renewal_expires_at(
            sub=sub, plan=plan, today=today
        )

        days_late = (
            sub.days_late(renewed_on=today) if sub.status == SubscriptionStatus.EXPIRED else 0
        )

        updated = await self._repo.renew(
            sub_id,
            new_expires_at=resolved,
            days_late=days_late,
            created_by=caller_id,
        )
        await self._sync_member_status(sub.member_id, MemberStatus.ACTIVE)
        await self._session.commit()
        return updated

    async def change_plan(
        self,
        *,
        caller: TokenPayload,
        sub_id: UUID,
        new_plan_id: UUID,
        effective_date: date | None = None,
    ) -> Subscription:
        """Upgrade / downgrade. Old sub → ``replaced``, new sub active with
        fresh price snapshot. Atomic — both rows land or neither does.

        Returns the NEW sub so the UI can navigate straight to it.
        """
        old, caller_id = await self._prepare_transition(caller, sub_id)
        if not old.can_change_plan():
            raise InvalidSubscriptionStateTransitionError(
                current=old.status.value, action="change plan"
            )
        if str(old.plan_id) == str(new_plan_id):
            raise SamePlanChangeError()

        new_plan = await self._plan_repo.find_by_id(new_plan_id)
        if new_plan is None:
            raise MembershipPlanNotFoundError(str(new_plan_id))
        if str(new_plan.tenant_id) != str(old.tenant_id):
            raise SubscriptionPlanMismatchError()
        if not new_plan.is_active:
            raise InvalidSubscriptionStateTransitionError(current="inactive", action="subscribe to")

        effective = effective_date or date.today()

        # Phase 1: old → replaced (replaced_by_id=NULL briefly). This
        # removes it from the partial-UNIQUE live-set so the new sub
        # can insert without collision.
        await self._repo.mark_replaced_pending(
            sub_id=old.id,
            replaced_at=effective,
            created_by=caller_id,
            event_data={
                "from_plan_id": str(old.plan_id),
                "to_plan_id": str(new_plan_id),
            },
        )

        # Phase 2: create the new active sub.
        new_sub = await self._repo.create(
            tenant_id=old.tenant_id,
            member_id=old.member_id,
            plan_id=new_plan_id,
            price_cents=new_plan.price_cents,
            currency=new_plan.currency,
            started_at=effective,
            expires_at=self._resolve_expires_at(
                plan=new_plan, started_at=effective, caller_override=None
            ),
            created_by=caller_id,
            event_data={
                "changed_from_subscription_id": str(old.id),
                "from_plan_id": str(old.plan_id),
            },
        )

        # Phase 3: link the old sub forward + write the companion event.
        await self._repo.set_replaced_by(old.id, replaced_by_id=new_sub.id)
        await self._repo.write_changed_plan_event(
            new_sub.id,
            from_sub_id=old.id,
            from_plan_id=old.plan_id,
            created_by=caller_id,
        )

        await self._sync_member_status(old.member_id, MemberStatus.ACTIVE)
        await self._session.commit()

        refreshed = await self._repo.find_by_id(new_sub.id)
        assert refreshed is not None
        return refreshed

    async def cancel(
        self,
        *,
        caller: TokenPayload,
        sub_id: UUID,
        reason: str | None = None,
        detail: str | None = None,
    ) -> Subscription:
        """Hard-terminal. Member actively left. Optional reason (canonical
        dropdown key: moved_away / too_expensive / not_using / injury / other)
        + free-text detail for analytics."""
        sub, caller_id = await self._prepare_transition(caller, sub_id)
        if not sub.can_cancel():
            raise InvalidSubscriptionStateTransitionError(current=sub.status.value, action="cancel")

        updated = await self._repo.cancel(
            sub_id,
            cancelled_at=date.today(),
            reason=reason,
            detail=detail,
            created_by=caller_id,
        )
        await self._sync_member_status(sub.member_id, MemberStatus.CANCELLED)
        await self._session.commit()
        return updated

    # ── Queries ──────────────────────────────────────────────────────────────

    async def get(self, *, caller: TokenPayload, sub_id: UUID) -> Subscription:
        """Fetch one sub. Tenant-scoped: cross-tenant → 404 (no existence leak)."""
        return await self._get_in_tenant(caller, sub_id)

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID | None = None,
        status: SubscriptionStatus | None = None,
        plan_id: UUID | None = None,
        expires_before: date | None = None,
        expires_within_days: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Subscription]:
        """List subs in the caller's tenant. Any tenant user can read."""
        tenant_id = self._require_tenant(caller)

        # expires_within_days is a convenience for the "about to expire"
        # dashboard — translate to an expires_before cutoff.
        effective_expires_before = expires_before
        if expires_within_days is not None:
            window_cutoff = date.today() + timedelta(days=expires_within_days)
            if effective_expires_before is None or window_cutoff < effective_expires_before:
                effective_expires_before = window_cutoff

        return await self._repo.list_for_tenant(
            tenant_id,
            member_id=member_id,
            status=status,
            plan_id=plan_id,
            expires_before=effective_expires_before,
            limit=limit,
            offset=offset,
        )

    async def list_for_member(self, *, caller: TokenPayload, member_id: UUID) -> list[Subscription]:
        """Full sub history for one member."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_member(tenant_id, member_id)

    async def get_current_for_member(
        self, *, caller: TokenPayload, member_id: UUID
    ) -> Subscription | None:
        """Current live sub (active or frozen) for a member."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.find_live_for_member(tenant_id, member_id)

    async def list_events(self, *, caller: TokenPayload, sub_id: UUID) -> list[SubscriptionEvent]:
        """Timeline of events for a sub. Service verifies tenant scope on
        the sub, then returns events."""
        await self._get_in_tenant(caller, sub_id)
        return await self._repo.list_events(sub_id)

    # ── Scheduled-job entrypoints (called by Celery beat) ────────────────────

    async def auto_unfreeze_due(self) -> int:
        """Nightly job: flip frozen subs whose ``frozen_until`` has passed
        back to ``active``, extending ``expires_at`` by the frozen duration.
        Writes system events (created_by=None). Returns count moved."""
        today = date.today()
        due = await self._repo.find_due_for_unfreeze(today=today)
        count = 0
        for sub in due:
            new_expires_at = self._extend_expires_for_unfreeze(sub, today=today)
            await self._repo.unfreeze(
                sub.id,
                today=today,
                new_expires_at=new_expires_at,
                created_by=None,
                auto=True,
            )
            await self._sync_member_status(sub.member_id, MemberStatus.ACTIVE)
            count += 1
        await self._session.commit()
        return count

    async def auto_expire_due(self) -> int:
        """Nightly job: flip active subs whose ``expires_at`` is in the past
        to ``expired``. Writes system events. Returns count moved."""
        today = date.today()
        due = await self._repo.find_due_for_expire(today=today)
        count = 0
        for sub in due:
            await self._repo.expire(sub.id, today=today)
            await self._sync_member_status(sub.member_id, MemberStatus.EXPIRED)
            count += 1
        await self._session.commit()
        return count

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _prepare_transition(
        self, caller: TokenPayload, sub_id: UUID
    ) -> tuple[Subscription, UUID | None]:
        """Shared pre-transition plumbing: role gate + tenant-scoped fetch +
        return the caller's UUID for the event's created_by."""
        sub = await self._get_in_tenant(caller, sub_id)
        self._require_staff(caller)
        return sub, self._caller_uuid(caller)

    async def _get_in_tenant(self, caller: TokenPayload, sub_id: UUID) -> Subscription:
        """Fetch + verify tenant match, or raise SubscriptionNotFoundError.

        super_admin bypasses scoping (platform support). Tenant users see
        only their own gym's subs; other-tenant lookup returns 404, not
        403 (no existence leak).
        """
        sub = await self._repo.find_by_id(sub_id)
        if sub is None:
            raise SubscriptionNotFoundError(str(sub_id))
        if caller.role == Role.SUPER_ADMIN.value:
            return sub
        if caller.tenant_id is None or str(sub.tenant_id) != str(caller.tenant_id):
            raise SubscriptionNotFoundError(str(sub_id))
        return sub

    async def _sync_member_status(self, member_id: UUID, new_status: MemberStatus) -> None:
        """Keep members.status in lockstep with the current sub's status.

        Called inside the same transaction as every sub state change.
        Option B of the member/sub sync design — see docs/features/subscriptions.md.
        """
        await self._member_repo.update(member_id, status=new_status)

    @staticmethod
    def _resolve_expires_at(
        *,
        plan,
        started_at: date,
        caller_override: date | None,
    ) -> date | None:
        """Derive expires_at per the cash-vs-card model:

        - Caller gave explicit value → trust it (cash / prepaid / trial-adjust).
        - Plan is one-time + no override → auto = started_at + duration_days.
        - Plan is recurring + no override → None (card-auto runs until cancelled).
        """
        if caller_override is not None:
            return caller_override
        if plan.type == PlanType.ONE_TIME and plan.duration_days is not None:
            return started_at + timedelta(days=plan.duration_days)
        return None

    @staticmethod
    def _default_renewal_expires_at(*, sub: Subscription, plan, today: date) -> date:
        """Default extension if the caller doesn't pass ``new_expires_at``:

        - active + has expires_at → push forward from max(today, expires_at).
        - expired → push forward from today (not expired_at; no double-paying
          for the lapse period).
        - active + expires_at is None → caller should've passed explicit; we
          fall back to today + billing_period days but this path is odd.
        """
        base = today
        if sub.status == SubscriptionStatus.ACTIVE and sub.expires_at is not None:
            base = max(today, sub.expires_at)

        if plan.type == PlanType.ONE_TIME and plan.duration_days is not None:
            return base + timedelta(days=plan.duration_days)
        days = _BILLING_PERIOD_DAYS.get(plan.billing_period, 30)
        return base + timedelta(days=days)

    @staticmethod
    def _extend_expires_for_unfreeze(sub: Subscription, *, today: date) -> date | None:
        """Push expires_at forward by the frozen duration. Returns None for
        card-auto subs (expires_at was None)."""
        if sub.expires_at is None or sub.frozen_at is None:
            return sub.expires_at
        frozen_days = (today - sub.frozen_at).days
        return sub.expires_at + timedelta(days=max(0, frozen_days))

    # ── Role / tenant helpers ────────────────────────────────────────────────

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> _UUID:
        """Reads allowed for any tenant user + super_admin.

        For super_admin we don't have a tenant_id — the caller must not
        invoke tenant-scoped reads. Routes that allow super_admin across
        tenants use ``_get_in_tenant`` directly instead of this helper.
        """
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_staff(caller: TokenPayload) -> None:
        """Mutations require staff / owner / super_admin. Sales is excluded."""
        if caller.role not in (
            Role.STAFF.value,
            Role.OWNER.value,
            Role.SUPER_ADMIN.value,
        ):
            raise InsufficientPermissionsError()

    def _require_staff_in_tenant(self, caller: TokenPayload) -> _UUID:
        self._require_staff(caller)
        return self._require_tenant(caller)

    @staticmethod
    def _caller_uuid(caller: TokenPayload) -> _UUID | None:
        """Return caller's user id (from JWT ``sub`` claim) as UUID.

        Event rows' ``created_by`` FK is nullable, so malformed tokens or
        system callers resolve to None rather than raising.
        """
        if caller.sub is None:
            return None
        try:
            return _UUID(caller.sub)
        except (TypeError, ValueError):
            return None
