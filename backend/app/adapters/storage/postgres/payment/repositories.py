"""Repository for the ``payments`` table.

Translates between ``PaymentORM`` (persistence) and ``Payment`` (domain).
Tenant scoping is enforced at the service layer — this repo accepts
raw tenant_id parameters and trusts the service to pass the right one.

Append-only: there is **no** ``update`` method. Refunds are new rows
inserted via ``create_refund`` (which the service calls after computing
the signed amount). Mistaken corrections happen the same way.

Dashboard reports lean on the range-sum helpers (``sum_for_range``,
``sum_by_plan_for_range``, ``sum_by_method_for_range``). Each is a
single SQL ``SUM`` aggregate — no application-side iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.adapters.storage.postgres.payment.models import PaymentORM
from app.adapters.storage.postgres.subscription.models import SubscriptionORM
from app.domain.entities.payment import Payment
from app.domain.entities.subscription import PaymentMethod

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PlanRevenueRow:
    """Per-plan revenue aggregate for the dashboard 'by plan' chart."""

    plan_id: UUID
    cents: int


def _to_domain(orm: PaymentORM) -> Payment:
    return Payment(
        id=orm.id,
        tenant_id=orm.tenant_id,
        member_id=orm.member_id,
        subscription_id=orm.subscription_id,
        amount_cents=int(orm.amount_cents),
        currency=orm.currency,
        payment_method=PaymentMethod(orm.payment_method),
        paid_at=orm.paid_at,
        notes=orm.notes,
        refund_of_payment_id=orm.refund_of_payment_id,
        external_ref=orm.external_ref,
        recorded_by=orm.recorded_by,
        created_at=orm.created_at,
    )


class PaymentRepository:
    """CRUD + range-sum aggregates. Owns no transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Writes ───────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: UUID,
        member_id: UUID,
        amount_cents: int,
        currency: str,
        payment_method: PaymentMethod,
        paid_at: date,
        subscription_id: UUID | None = None,
        notes: str | None = None,
        refund_of_payment_id: UUID | None = None,
        external_ref: str | None = None,
        recorded_by: UUID | None = None,
    ) -> Payment:
        """Insert a payment row. Used by both record and refund flows
        (the service computes the signed amount + sets
        ``refund_of_payment_id`` on the refund path)."""
        orm = PaymentORM(
            tenant_id=tenant_id,
            member_id=member_id,
            subscription_id=subscription_id,
            amount_cents=amount_cents,
            currency=currency,
            payment_method=payment_method.value,
            paid_at=paid_at,
            notes=notes,
            refund_of_payment_id=refund_of_payment_id,
            external_ref=external_ref,
            recorded_by=recorded_by,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    # ── Reads ────────────────────────────────────────────────────────

    async def find_by_id(self, payment_id: UUID) -> Payment | None:
        result = await self._session.execute(select(PaymentORM).where(PaymentORM.id == payment_id))
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        member_id: UUID | None = None,
        subscription_id: UUID | None = None,
        paid_from: date | None = None,
        paid_to: date | None = None,
        method: PaymentMethod | None = None,
        include_refunds: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        stmt = select(PaymentORM).where(PaymentORM.tenant_id == tenant_id)
        if member_id is not None:
            stmt = stmt.where(PaymentORM.member_id == member_id)
        if subscription_id is not None:
            stmt = stmt.where(PaymentORM.subscription_id == subscription_id)
        if paid_from is not None:
            stmt = stmt.where(PaymentORM.paid_at >= paid_from)
        if paid_to is not None:
            stmt = stmt.where(PaymentORM.paid_at <= paid_to)
        if method is not None:
            stmt = stmt.where(PaymentORM.payment_method == method.value)
        if not include_refunds:
            stmt = stmt.where(PaymentORM.refund_of_payment_id.is_(None))
        stmt = (
            stmt.order_by(PaymentORM.paid_at.desc(), PaymentORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    async def list_for_member(
        self, tenant_id: UUID, member_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Payment]:
        return await self.list_for_tenant(
            tenant_id, member_id=member_id, limit=limit, offset=offset
        )

    async def list_refunds_for(self, payment_id: UUID) -> list[Payment]:
        """Return all refund rows pointing at the given payment.
        Ordered oldest-first so the cumulative-refunded math reads naturally."""
        stmt = (
            select(PaymentORM)
            .where(PaymentORM.refund_of_payment_id == payment_id)
            .order_by(PaymentORM.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]

    # ── Aggregates (dashboard) ───────────────────────────────────────

    async def sum_for_range(self, tenant_id: UUID, *, paid_from: date, paid_to: date) -> int:
        """Net revenue (refunds subtract automatically because they're
        negative rows) for a date range, inclusive on both ends."""
        stmt = select(func.coalesce(func.sum(PaymentORM.amount_cents), 0)).where(
            PaymentORM.tenant_id == tenant_id,
            PaymentORM.paid_at >= paid_from,
            PaymentORM.paid_at <= paid_to,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def sum_by_plan_for_range(
        self, tenant_id: UUID, *, paid_from: date, paid_to: date
    ) -> list[PlanRevenueRow]:
        """Revenue grouped by ``subscriptions.plan_id``. Drop-in payments
        (subscription_id NULL) are excluded — they have no plan to group
        by; the caller surfaces them via ``sum_for_range`` minus the
        sum-of-by-plan if they want a "drop-ins" bucket."""
        stmt = (
            select(
                SubscriptionORM.plan_id,
                func.coalesce(func.sum(PaymentORM.amount_cents), 0).label("cents"),
            )
            .join(SubscriptionORM, PaymentORM.subscription_id == SubscriptionORM.id)
            .where(
                PaymentORM.tenant_id == tenant_id,
                PaymentORM.paid_at >= paid_from,
                PaymentORM.paid_at <= paid_to,
            )
            .group_by(SubscriptionORM.plan_id)
            .order_by(func.sum(PaymentORM.amount_cents).desc())
        )
        result = await self._session.execute(stmt)
        return [PlanRevenueRow(plan_id=row[0], cents=int(row[1])) for row in result.all()]

    async def sum_by_method_for_range(
        self, tenant_id: UUID, *, paid_from: date, paid_to: date
    ) -> dict[str, int]:
        """Revenue grouped by payment method (cash / credit_card / ...).
        Includes refund rows with their respective methods (so a
        refunded credit-card charge nets correctly)."""
        stmt = (
            select(
                PaymentORM.payment_method,
                func.coalesce(func.sum(PaymentORM.amount_cents), 0),
            )
            .where(
                PaymentORM.tenant_id == tenant_id,
                PaymentORM.paid_at >= paid_from,
                PaymentORM.paid_at <= paid_to,
            )
            .group_by(PaymentORM.payment_method)
        )
        result = await self._session.execute(stmt)
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_distinct_paying_members(
        self, tenant_id: UUID, *, paid_from: date, paid_to: date
    ) -> int:
        """For ARPM (avg revenue per paying member) — the denominator.

        Counts distinct members who had ANY payment in the window
        (including refund rows — a member who paid then got fully
        refunded still counts as a "paying member" for the period; the
        revenue sum reflects the net zero, but the count keeps them
        visible)."""
        stmt = select(func.count(func.distinct(PaymentORM.member_id))).where(
            PaymentORM.tenant_id == tenant_id,
            PaymentORM.paid_at >= paid_from,
            PaymentORM.paid_at <= paid_to,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
