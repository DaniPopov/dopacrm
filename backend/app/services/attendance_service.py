"""Attendance (check-in) service — Layer 2.

The feature that validates the Plans + Subscriptions entitlement model
in practice. Every design decision in those upstream features is
exercised here:

- Each entry needs a LIVE subscription (active or frozen per the
  subscription partial-UNIQUE predicate). No subscriptionless entries.
- Entitlements are consulted per-entry: exact-class match beats
  any-class wildcard. `unlimited` reset_period short-circuits the quota.
- Reset-window math lives in ``compute_window_start`` — the one place
  the rolling-week / calendar-month / billing-period / never / unlimited
  semantics translate into a concrete "since" datetime.
- Overrides are not blocked at the service layer — staff can pass
  ``override=True`` to bypass quota and not-covered. Each override is
  tagged so the owner's audit surface can pick it up.
- Every mutation emits a structured log event for Loki/Grafana.

Observability:
    attendance.recorded   — fires on every successful check-in
    attendance.override   — fires on every override (subset of recorded)
    attendance.undone     — fires on every undo
    attendance.quota_check— fires on every /quota-check (sampled)

All times in this file are UTC. The reset-window boundaries for
``weekly`` / ``monthly`` are computed in UTC too — we accept a 1-day
drift for Israel gyms vs strict Asia/Jerusalem calendar weeks. Fix
when a non-UTC tenant onboards.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID as _UUID

from pydantic import BaseModel

from app.adapters.storage.postgres.class_entry.repositories import (
    ClassEntryRepository,
)
from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.core.time import utcnow
from app.domain.entities.class_entry import UNDO_WINDOW, ClassEntry, OverrideKind
from app.domain.entities.membership_plan import (
    BillingPeriod,
    PlanEntitlement,
    ResetPeriod,
)
from app.domain.entities.subscription import Subscription, SubscriptionStatus
from app.domain.entities.user import Role
from app.domain.exceptions import (
    ClassEntryAlreadyUndoneError,
    ClassEntryNotFoundError,
    ClassNotCoveredByPlanError,
    InsufficientPermissionsError,
    MemberHasNoActiveSubscriptionError,
    MembershipPlanNotFoundError,
    QuotaExceededError,
    UndoWindowExpiredError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload

logger = logging.getLogger(__name__)

# Map the plan's billing_period onto day counts for BILLING_PERIOD-scoped
# entitlements. Matches SubscriptionService._default_renewal_expires_at.
_BILLING_PERIOD_DAYS = {
    BillingPeriod.MONTHLY: 30,
    BillingPeriod.QUARTERLY: 90,
    BillingPeriod.YEARLY: 365,
}


# ── Quota-check result (API + service use the same shape) ─────────────


class QuotaCheckResult(BaseModel):
    """Outcome of the quota-check for one (member, class) pair.

    - ``allowed=True, remaining=None`` — UNLIMITED entitlement (no cap).
    - ``allowed=True, remaining=N``   — metered, staff can record N more.
    - ``allowed=False, reason=...``   — staff must override to record.
    """

    allowed: bool
    remaining: int | None = None
    used: int | None = None
    quantity: int | None = None
    reset_period: str | None = None
    #: One of 'quota_exceeded' / 'not_covered' when allowed=False.
    reason: str | None = None


# ── Service ───────────────────────────────────────────────────────────


class AttendanceService:
    """Check-in operations with quota enforcement + structlog audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ClassEntryRepository(session)
        self._member_repo = MemberRepository(session)
        self._sub_repo = SubscriptionRepository(session)

    # ── Commands ─────────────────────────────────────────────────────────

    async def record_entry(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
        class_id: UUID,
        override: bool = False,
        override_reason: str | None = None,
    ) -> ClassEntry:
        """Record one check-in. The full pipeline:

        1. Role + tenant scoping (staff+).
        2. Find member's live subscription — 409 if none.
        3. Quota-check (see ``quota_check``):
           - allowed → record normally.
           - disallowed + override=False → raise typed error (UI shows
             the override modal; staff retries with override=True).
           - disallowed + override=True → record with ``override=True``
             and the right ``override_kind``.
        4. Insert, commit, log.
        """
        tenant_id = self._require_staff_in_tenant(caller)
        caller_id = self._caller_uuid(caller)

        sub = await self._sub_repo.find_live_for_member(tenant_id, member_id)
        if sub is None:
            raise MemberHasNoActiveSubscriptionError(str(member_id))

        check = await self._quota_check_for_sub(sub=sub, class_id=class_id, now=utcnow())

        # Map the check into the (override, kind) tuple the repo takes.
        override_kind: OverrideKind | None = None
        if not check.allowed:
            if not override:
                if check.reason == "quota_exceeded":
                    raise QuotaExceededError(used=check.used or 0, quantity=check.quantity or 0)
                raise ClassNotCoveredByPlanError(str(class_id))
            override_kind = (
                OverrideKind.QUOTA_EXCEEDED
                if check.reason == "quota_exceeded"
                else OverrideKind.NOT_COVERED
            )

        entry = await self._repo.create(
            tenant_id=tenant_id,
            member_id=member_id,
            subscription_id=sub.id,
            class_id=class_id,
            entered_by=caller_id,
            override=override_kind is not None,
            override_kind=override_kind,
            override_reason=override_reason if override_kind else None,
        )
        await self._session.commit()

        logger.info(
            "attendance.recorded",
            extra={
                "event": "attendance.recorded",
                "tenant_id": str(tenant_id),
                "entry_id": str(entry.id),
                "member_id": str(member_id),
                "class_id": str(class_id),
                "subscription_id": str(sub.id),
                "entered_by": str(caller_id) if caller_id else None,
                "override": entry.override,
                "override_kind": entry.override_kind.value if entry.override_kind else None,
                "quota_remaining": check.remaining,
            },
        )
        if entry.override:
            logger.info(
                "attendance.override",
                extra={
                    "event": "attendance.override",
                    "tenant_id": str(tenant_id),
                    "entry_id": str(entry.id),
                    "staff_id": str(caller_id) if caller_id else None,
                    "kind": entry.override_kind.value if entry.override_kind else None,
                    "reason": entry.override_reason,
                },
            )
        return entry

    async def undo(
        self,
        *,
        caller: TokenPayload,
        entry_id: UUID,
        reason: str | None = None,
    ) -> ClassEntry:
        """Soft-delete an entry within the 24h window. Staff who created
        the entry or owner+ can undo. Service is permissive on who —
        owner can always undo, any staff in the same tenant can undo any
        entry (keeps the front-desk flow simple; swap to stricter
        creator-or-owner if abuse shows up)."""
        tenant_id = self._require_staff_in_tenant(caller)
        caller_id = self._caller_uuid(caller)

        entry = await self._get_in_tenant(caller, entry_id, tenant_id)
        now = utcnow()
        if entry.undone_at is not None:
            raise ClassEntryAlreadyUndoneError(str(entry_id))
        if not entry.can_undo(now=now):
            hours = entry.age(now).total_seconds() / 3600
            raise UndoWindowExpiredError(hours_since_entry=hours)

        updated = await self._repo.undo(
            entry_id,
            undone_at=now,
            undone_by=caller_id,
            undone_reason=reason,
        )
        await self._session.commit()

        logger.info(
            "attendance.undone",
            extra={
                "event": "attendance.undone",
                "tenant_id": str(tenant_id),
                "entry_id": str(entry_id),
                "undone_by": str(caller_id) if caller_id else None,
                "hours_since_entry": entry.age(now).total_seconds() / 3600,
                "reason": reason,
            },
        )
        return updated

    # ── Queries ──────────────────────────────────────────────────────────

    async def quota_check(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID,
        class_id: UUID,
    ) -> QuotaCheckResult:
        """Peek at whether a check-in would be allowed. Does NOT record
        anything. Used by the check-in page to color class cards
        (covered / not covered / at-quota with remaining count)."""
        tenant_id = self._require_tenant(caller)
        sub = await self._sub_repo.find_live_for_member(tenant_id, member_id)
        if sub is None:
            raise MemberHasNoActiveSubscriptionError(str(member_id))

        result = await self._quota_check_for_sub(sub=sub, class_id=class_id, now=utcnow())
        logger.debug(
            "attendance.quota_check",
            extra={
                "event": "attendance.quota_check",
                "tenant_id": str(tenant_id),
                "member_id": str(member_id),
                "class_id": str(class_id),
                "allowed": result.allowed,
                "reason": result.reason,
                "remaining": result.remaining,
            },
        )
        return result

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        member_id: UUID | None = None,
        class_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_undone: bool = False,
        undone_only: bool = False,
        override_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClassEntry]:
        """Owner/staff list view. Filters for dashboards + owner audits."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_tenant(
            tenant_id,
            member_id=member_id,
            class_id=class_id,
            date_from=date_from,
            date_to=date_to,
            include_undone=include_undone,
            undone_only=undone_only,
            override_only=override_only,
            limit=limit,
            offset=offset,
        )

    async def list_for_member(
        self, *, caller: TokenPayload, member_id: UUID, limit: int = 50
    ) -> list[ClassEntry]:
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_member(tenant_id, member_id, limit=limit)

    async def summary_for_member(
        self, *, caller: TokenPayload, member_id: UUID
    ) -> list[QuotaCheckResult]:
        """Per-entitlement usage summary for the check-in page header.

        Returns one QuotaCheckResult per entitlement on the member's live
        sub. UNLIMITED entitlements show up with ``remaining=None``.
        No sub → empty list.
        """
        tenant_id = self._require_tenant(caller)
        sub = await self._sub_repo.find_live_for_member(tenant_id, member_id)
        if sub is None:
            return []

        now = utcnow()
        results: list[QuotaCheckResult] = []
        for ent in (await self._resolve_entitlements(sub)) or []:
            results.append(await self._quota_for_entitlement(sub=sub, entitlement=ent, now=now))
        return results

    # ── Private helpers ──────────────────────────────────────────────────

    async def _get_in_tenant(
        self, caller: TokenPayload, entry_id: UUID, tenant_id: _UUID
    ) -> ClassEntry:
        """Fetch + verify tenant match, or raise ClassEntryNotFoundError."""
        entry = await self._repo.find_by_id(entry_id)
        if entry is None:
            raise ClassEntryNotFoundError(str(entry_id))
        if caller.role == Role.SUPER_ADMIN.value:
            return entry
        if str(entry.tenant_id) != str(tenant_id):
            raise ClassEntryNotFoundError(str(entry_id))
        return entry

    async def _quota_check_for_sub(
        self, *, sub: Subscription, class_id: UUID, now: datetime
    ) -> QuotaCheckResult:
        """Find the matching entitlement (exact > wildcard) and evaluate.

        No match → ``not_covered``. UNLIMITED → allow. Otherwise count
        effective entries since window start and compare against quota.
        """
        entitlements = await self._resolve_entitlements(sub)
        match = _find_matching_entitlement(entitlements, class_id)
        if match is None:
            return QuotaCheckResult(allowed=False, reason="not_covered")
        return await self._quota_for_entitlement(sub=sub, entitlement=match, now=now)

    async def _quota_for_entitlement(
        self, *, sub: Subscription, entitlement: PlanEntitlement, now: datetime
    ) -> QuotaCheckResult:
        """Count usage + compare to quantity. UNLIMITED short-circuits."""
        if entitlement.reset_period == ResetPeriod.UNLIMITED:
            return QuotaCheckResult(
                allowed=True,
                reset_period=entitlement.reset_period.value,
            )

        plan = await self._resolve_plan(sub)
        window_start = _compute_window_start(
            reset_period=entitlement.reset_period,
            now=now,
            sub_started_at=sub.started_at,
            billing_period=plan.billing_period if plan else BillingPeriod.MONTHLY,
        )
        # class_id=None on entitlement = any-class wildcard
        count = await self._repo.count_effective_entries(
            member_id=sub.member_id,
            class_id=entitlement.class_id,
            since=window_start,
        )
        quantity = entitlement.quantity or 0
        remaining = max(0, quantity - count)
        allowed = count < quantity
        return QuotaCheckResult(
            allowed=allowed,
            used=count,
            quantity=quantity,
            remaining=remaining,
            reset_period=entitlement.reset_period.value,
            reason=None if allowed else "quota_exceeded",
        )

    async def _resolve_entitlements(self, sub: Subscription) -> list[PlanEntitlement]:
        """Return the entitlements on the sub's plan. The sub repo's
        find_by_id doesn't eager-load plan entitlements, so we fetch
        via the plan repo — one extra query per quota check. Cheap."""
        from app.adapters.storage.postgres.membership_plan.repositories import (
            MembershipPlanRepository,
        )

        plan_repo = MembershipPlanRepository(self._session)
        plan = await plan_repo.find_by_id(sub.plan_id)
        return plan.entitlements if plan else []

    async def _resolve_plan(self, sub: Subscription):
        """Fetch the sub's plan (for billing_period lookup)."""
        from app.adapters.storage.postgres.membership_plan.repositories import (
            MembershipPlanRepository,
        )

        plan_repo = MembershipPlanRepository(self._session)
        plan = await plan_repo.find_by_id(sub.plan_id)
        if plan is None:
            # FK RESTRICT should prevent this. Defensive.
            raise MembershipPlanNotFoundError(str(sub.plan_id))
        return plan

    # ── Role / tenant helpers ────────────────────────────────────────────

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> _UUID:
        """Any tenant user can read. super_admin rejected (no tenant scope)."""
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_staff(caller: TokenPayload) -> None:
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
        if caller.sub is None:
            return None
        try:
            return _UUID(caller.sub)
        except (TypeError, ValueError):
            return None


# ── Pure helpers (testable without DB) ─────────────────────────────────


def _find_matching_entitlement(
    entitlements: list[PlanEntitlement], class_id: UUID
) -> PlanEntitlement | None:
    """Exact-class match wins over any-class wildcard.

    Precedence: if the plan has both "3 yoga/week" AND "unlimited any-class",
    a yoga entry counts against the 3/week rule. A spinning entry hits
    the unlimited rule.
    """
    exact = next(
        (e for e in entitlements if e.class_id is not None and str(e.class_id) == str(class_id)),
        None,
    )
    if exact is not None:
        return exact
    return next((e for e in entitlements if e.class_id is None), None)


def _compute_window_start(
    *,
    reset_period: ResetPeriod,
    now: datetime,
    sub_started_at: date,
    billing_period: BillingPeriod,
) -> datetime:
    """Turn a ResetPeriod into a concrete "since" timestamp.

    All boundaries in UTC. For IL gyms a weekly reset of "Sunday 00:00
    UTC" is roughly "Sunday 02:00-03:00 Israel" (a few hours off true
    midnight-local). Acceptable drift for v1; add per-tenant timezone
    later if it matters.
    """
    if reset_period == ResetPeriod.WEEKLY:
        # Rolling week: Sunday 00:00 UTC.
        # In Python, Monday=0 .. Sunday=6. Convert to Sunday-indexed.
        days_since_sunday = (now.weekday() + 1) % 7
        start = (now - timedelta(days=days_since_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start
    if reset_period == ResetPeriod.MONTHLY:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if reset_period == ResetPeriod.BILLING_PERIOD:
        # The current billing cycle — from sub_started_at + N * billing_period_days.
        days = _BILLING_PERIOD_DAYS.get(billing_period, 30)
        start_dt = datetime.combine(sub_started_at, datetime.min.time(), tzinfo=UTC)
        elapsed = now - start_dt
        cycles_done = elapsed.days // days
        return start_dt + timedelta(days=cycles_done * days)
    if reset_period == ResetPeriod.NEVER:
        # Total across the sub's lifetime.
        return datetime.combine(sub_started_at, datetime.min.time(), tzinfo=UTC)
    if reset_period == ResetPeriod.UNLIMITED:
        # Shouldn't be called in this path (caller short-circuits), but
        # return a far-past sentinel just in case.
        return datetime(1970, 1, 1, tzinfo=UTC)
    # Unknown reset_period — defensive, treat as NEVER.
    return datetime.combine(sub_started_at, datetime.min.time(), tzinfo=UTC)


# Re-export sentinel for other modules
__all__ = [
    "AttendanceService",
    "QuotaCheckResult",
    "UNDO_WINDOW",
    "SubscriptionStatus",
    "_compute_window_start",
    "_find_matching_entitlement",
]
