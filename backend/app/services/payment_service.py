"""Payment service — orchestrates the gym's revenue ledger.

Layer 2. Owns:

- **Record.** Insert a positive-amount payment row tied to a member +
  optional subscription. Currency snapshot from ``tenants.currency``.
  Caller's tenant + role gates enforced.
- **Refund.** Insert a *new* row with negative ``amount_cents`` and
  ``refund_of_payment_id`` pointing at the original. Append-only —
  the original stays. Cumulative-refunded math enforces "can't refund
  more than was originally collected" with two distinct typed errors
  (`PAYMENT_REFUND_EXCEEDS_ORIGINAL` vs
  `PAYMENT_ALREADY_FULLY_REFUNDED`) so the UI can show the right
  message + hide the refund button when nothing's left.
- **Reads.** List with filters; member-scoped list (the member detail
  page); a single by-id; the dashboard ``revenue_summary``.

No ``update`` method, no ``delete`` method. Append-only is enforced
both at the API layer (no PATCH/DELETE routes) and here (no service
methods). Mistakes get a corrective negative-amount row.

Permissions:

- **owner / super_admin / staff / sales** — write payments + read.
- **owner / super_admin** — refund. Staff/sales can record but can't
  refund (destructive-ish; owner-gated to prevent honest staff
  mistakes from corrupting the books).
- **coach** — no access at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING
from uuid import UUID as _UUID

from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.payment.repositories import (
    PaymentRepository,
    PlanRevenueRow,
)
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.user import Role
from app.domain.exceptions import (
    InsufficientPermissionsError,
    MemberNotFoundError,
    PaymentAlreadyFullyRefundedError,
    PaymentAmountInvalidError,
    PaymentNotFoundError,
    PaymentRefundExceedsOriginalError,
    SubscriptionNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload
    from app.domain.entities.payment import Payment
    from app.domain.entities.subscription import PaymentMethod


logger = logging.getLogger(__name__)


#: Default backdate window. ``paid_at`` more than this many days ago
#: requires the explicit ``backdate=True`` flag — small friction
#: against typos that would land in last year's revenue report.
DEFAULT_BACKDATE_LIMIT_DAYS: int = 30


# ── DTOs ──────────────────────────────────────────────────────────────


@dataclass
class RangeRevenue:
    """Revenue total for a date range (this-month / last-month / etc.)."""

    paid_from: date
    paid_to: date
    cents: int


@dataclass
class RevenueSummary:
    """Backs the dashboard 'revenue' widgets — see
    ``GET /api/v1/dashboard/revenue``."""

    currency: str
    this_month: RangeRevenue
    last_month: RangeRevenue
    #: Net month-over-month change as a percentage. None when last_month
    #: is zero (avoids divide-by-zero).
    mom_pct: float | None
    by_plan: list[PlanRevenueRow] = field(default_factory=list)
    by_method: dict[str, int] = field(default_factory=dict)
    #: Average revenue per paying member in ``this_month``. Cents.
    arpm_cents: int = 0


# ── Service ───────────────────────────────────────────────────────────


class PaymentService:
    """Record + refund + list + dashboard summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PaymentRepository(session)
        self._member_repo = MemberRepository(session)
        self._sub_repo = SubscriptionRepository(session)
        self._tenant_repo = TenantRepository(session)

    # ── Record ──────────────────────────────────────────────────────

    async def record(
        self,
        *,
        caller: TokenPayload,
        member_id: _UUID,
        amount_cents: int,
        payment_method: PaymentMethod,
        paid_at: date | None = None,
        subscription_id: _UUID | None = None,
        notes: str | None = None,
        external_ref: str | None = None,
        backdate: bool = False,
    ) -> Payment:
        """Insert a new (positive-amount) payment row.

        - ``paid_at`` defaults to today (in the server's local date —
          tenant timezone refinement is a future concern).
        - Future-dated entries are rejected (probably a typo).
        - Backdate up to ``DEFAULT_BACKDATE_LIMIT_DAYS`` is allowed by
          default; further back requires ``backdate=True``.
        - ``amount_cents`` must be **positive**. Refunds go through the
          dedicated ``refund`` method so the math is computed
          server-side.
        """
        tenant_id = self._require_writer_in_tenant(caller)

        if amount_cents <= 0:
            raise PaymentAmountInvalidError("amount_cents must be positive")

        resolved_paid_at = paid_at or date.today()
        if resolved_paid_at > date.today():
            raise PaymentAmountInvalidError(
                f"paid_at cannot be in the future: {resolved_paid_at.isoformat()}"
            )
        days_back = (date.today() - resolved_paid_at).days
        if days_back > DEFAULT_BACKDATE_LIMIT_DAYS and not backdate:
            raise PaymentAmountInvalidError(
                f"paid_at is {days_back} days in the past — set backdate=true to allow"
            )

        # Cross-resource validation.
        await self._assert_member_in_tenant(member_id, tenant_id)
        if subscription_id is not None:
            await self._assert_subscription_in_tenant(subscription_id, tenant_id, member_id)

        currency = await self._tenant_currency(tenant_id)

        payment = await self._repo.create(
            tenant_id=tenant_id,
            member_id=member_id,
            subscription_id=subscription_id,
            amount_cents=amount_cents,
            currency=currency,
            payment_method=payment_method,
            paid_at=resolved_paid_at,
            notes=notes,
            external_ref=external_ref,
            recorded_by=self._caller_uuid(caller),
        )
        await self._session.commit()

        logger.info(
            "payment.recorded",
            extra={
                "event": "payment.recorded",
                "tenant_id": str(tenant_id),
                "payment_id": str(payment.id),
                "member_id": str(member_id),
                "subscription_id": str(subscription_id) if subscription_id else None,
                "amount_cents": amount_cents,
                "method": payment_method.value,
                "paid_at": resolved_paid_at.isoformat(),
            },
        )
        return payment

    # ── Refund ──────────────────────────────────────────────────────

    async def refund(
        self,
        *,
        caller: TokenPayload,
        payment_id: _UUID,
        amount_cents: int | None = None,
        reason: str | None = None,
    ) -> Payment:
        """Record a refund row pointing at ``payment_id``.

        - ``amount_cents=None`` → full refund of the remaining
          refundable amount.
        - ``amount_cents=N`` (positive int) → partial refund of exactly N.
          The service flips the sign before insert (the row stores
          ``-N``).
        - Cumulative-refunded math: if (already-refunded + new-refund) >
          original, raises ``PaymentRefundExceedsOriginalError``.
          If already-refunded == original, raises
          ``PaymentAlreadyFullyRefundedError`` (lets the UI hide the
          button instead of showing an error).
        - Refund-of-refund is blocked: the original row's
          ``refund_of_payment_id`` must be NULL.
        """
        tenant_id = self._require_owner_in_tenant(caller)

        original = await self._repo.find_by_id(payment_id)
        if original is None or str(original.tenant_id) != str(tenant_id):
            raise PaymentNotFoundError(str(payment_id))
        if original.is_refund():
            raise PaymentAmountInvalidError(
                "cannot refund a refund row — refunds are append-only corrections"
            )

        if original.amount_cents <= 0:
            raise PaymentAmountInvalidError("cannot refund a non-positive payment row")

        # Cumulative refunds so far on this payment.
        existing_refunds = await self._repo.list_refunds_for(payment_id)
        already_refunded = sum(-r.amount_cents for r in existing_refunds)  # positive int
        remaining = original.amount_cents - already_refunded

        if remaining <= 0:
            raise PaymentAlreadyFullyRefundedError(str(payment_id))

        requested = amount_cents if amount_cents is not None else remaining
        if requested <= 0:
            raise PaymentAmountInvalidError("refund amount_cents must be positive")
        if requested > remaining:
            raise PaymentRefundExceedsOriginalError(
                str(payment_id), requested=requested, remaining=remaining
            )

        # Build the refund row's note. Reason is optional but useful
        # for audit; preserving it in the row keeps the timeline rich.
        note_parts = [f"refund of payment {payment_id}"]
        if reason:
            note_parts.append(f"reason: {reason.strip()}")

        refund_row = await self._repo.create(
            tenant_id=tenant_id,
            member_id=original.member_id,
            # Copy the subscription_id so revenue-per-plan reports
            # group correctly (refund subtracts from the same plan that
            # earned the original).
            subscription_id=original.subscription_id,
            amount_cents=-requested,  # signed
            currency=original.currency,
            payment_method=original.payment_method,
            paid_at=date.today(),
            notes="; ".join(note_parts),
            refund_of_payment_id=original.id,
            recorded_by=self._caller_uuid(caller),
        )
        await self._session.commit()

        logger.info(
            "payment.refunded",
            extra={
                "event": "payment.refunded",
                "tenant_id": str(tenant_id),
                "payment_id": str(refund_row.id),
                "original_payment_id": str(payment_id),
                "amount_cents": -requested,
                "reason": reason,
                "by": caller.sub,
            },
        )
        return refund_row

    # ── Reads ───────────────────────────────────────────────────────

    async def get(self, *, caller: TokenPayload, payment_id: _UUID) -> Payment:
        tenant_id = self._require_reader_in_tenant(caller)
        payment = await self._repo.find_by_id(payment_id)
        if payment is None or str(payment.tenant_id) != str(tenant_id):
            raise PaymentNotFoundError(str(payment_id))
        return payment

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        member_id: _UUID | None = None,
        subscription_id: _UUID | None = None,
        paid_from: date | None = None,
        paid_to: date | None = None,
        method: PaymentMethod | None = None,
        include_refunds: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        tenant_id = self._require_reader_in_tenant(caller)
        return await self._repo.list_for_tenant(
            tenant_id,
            member_id=member_id,
            subscription_id=subscription_id,
            paid_from=paid_from,
            paid_to=paid_to,
            method=method,
            include_refunds=include_refunds,
            limit=limit,
            offset=offset,
        )

    async def list_for_member(self, *, caller: TokenPayload, member_id: _UUID) -> list[Payment]:
        tenant_id = self._require_reader_in_tenant(caller)
        await self._assert_member_in_tenant(member_id, tenant_id)
        return await self._repo.list_for_member(tenant_id, member_id)

    async def revenue_summary(self, *, caller: TokenPayload) -> RevenueSummary:
        """Backs ``GET /api/v1/dashboard/revenue``. Computes
        this-month + last-month + MoM% + by-plan + by-method + ARPM."""
        tenant_id = self._require_reader_in_tenant(caller)

        today = date.today()
        this_from = today.replace(day=1)
        last_to = this_from - timedelta(days=1)
        last_from = last_to.replace(day=1)

        currency = await self._tenant_currency(tenant_id)

        this_cents = await self._repo.sum_for_range(tenant_id, paid_from=this_from, paid_to=today)
        last_cents = await self._repo.sum_for_range(tenant_id, paid_from=last_from, paid_to=last_to)
        if last_cents == 0:
            mom_pct: float | None = None
        else:
            mom_pct = round((this_cents - last_cents) / last_cents * 100, 1)

        by_plan = await self._repo.sum_by_plan_for_range(
            tenant_id, paid_from=this_from, paid_to=today
        )
        by_method = await self._repo.sum_by_method_for_range(
            tenant_id, paid_from=this_from, paid_to=today
        )

        paying = await self._repo.count_distinct_paying_members(
            tenant_id, paid_from=this_from, paid_to=today
        )
        arpm_cents = (this_cents // paying) if paying > 0 else 0

        return RevenueSummary(
            currency=currency,
            this_month=RangeRevenue(paid_from=this_from, paid_to=today, cents=this_cents),
            last_month=RangeRevenue(paid_from=last_from, paid_to=last_to, cents=last_cents),
            mom_pct=mom_pct,
            by_plan=by_plan,
            by_method=by_method,
            arpm_cents=arpm_cents,
        )

    # ── Cross-resource helpers ──────────────────────────────────────

    async def _assert_member_in_tenant(self, member_id: _UUID, tenant_id: _UUID) -> None:
        member = await self._member_repo.find_by_id(member_id)
        if member is None or str(member.tenant_id) != str(tenant_id):
            raise MemberNotFoundError(str(member_id))

    async def _assert_subscription_in_tenant(
        self, subscription_id: _UUID, tenant_id: _UUID, member_id: _UUID
    ) -> None:
        sub = await self._sub_repo.find_by_id(subscription_id)
        if sub is None or str(sub.tenant_id) != str(tenant_id):
            raise SubscriptionNotFoundError(str(subscription_id))
        # Belt-and-suspenders: a subscription tied to this payment must
        # belong to the same member. Surfaces as 404 to avoid leaking
        # cross-member sub existence.
        if str(sub.member_id) != str(member_id):
            raise SubscriptionNotFoundError(str(subscription_id))

    async def _tenant_currency(self, tenant_id: _UUID) -> str:
        tenant = await self._tenant_repo.find_by_id(tenant_id)
        return tenant.currency if tenant else "ILS"

    # ── Role + tenant gates ─────────────────────────────────────────

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> _UUID:
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_writer(caller: TokenPayload) -> None:
        """staff+ — staff, sales, owner, super_admin. Coach blocked."""
        if caller.role not in (
            Role.STAFF.value,
            Role.SALES.value,
            Role.OWNER.value,
            Role.SUPER_ADMIN.value,
        ):
            raise InsufficientPermissionsError()

    @staticmethod
    def _require_owner(caller: TokenPayload) -> None:
        """owner+ for refunds. Destructive-ish; owner-gated."""
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()

    @staticmethod
    def _require_reader(caller: TokenPayload) -> None:
        """Reads — every tenant role except coach."""
        if caller.role == Role.COACH.value:
            raise InsufficientPermissionsError()

    def _require_writer_in_tenant(self, caller: TokenPayload) -> _UUID:
        self._require_writer(caller)
        return self._require_tenant(caller)

    def _require_owner_in_tenant(self, caller: TokenPayload) -> _UUID:
        self._require_owner(caller)
        return self._require_tenant(caller)

    def _require_reader_in_tenant(self, caller: TokenPayload) -> _UUID:
        self._require_reader(caller)
        return self._require_tenant(caller)

    @staticmethod
    def _caller_uuid(caller: TokenPayload) -> _UUID | None:
        if caller.sub is None:
            return None
        try:
            return _UUID(caller.sub)
        except (TypeError, ValueError):
            return None


__all__ = ["PaymentService", "RevenueSummary", "RangeRevenue"]
