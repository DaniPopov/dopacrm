"""Repository for membership_plans + plan_entitlements.

Plans and their entitlements are loaded/saved as a unit — the domain
entity ``MembershipPlan.entitlements`` is the source of truth. The
service passes in a list of entitlements; the repo replaces the rows
atomically within the session transaction.

Tenant-scoping is the SERVICE's job. This repo trusts the service to
pass the right tenant_id and to have validated that referenced class_ids
belong to that tenant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.adapters.storage.postgres.membership_plan.models import (
    MembershipPlanORM,
    PlanEntitlementORM,
)
from app.domain.entities.membership_plan import (
    BillingPeriod,
    MembershipPlan,
    PlanEntitlement,
    PlanType,
    ResetPeriod,
)
from app.domain.exceptions import (
    MembershipPlanAlreadyExistsError,
    MembershipPlanNotFoundError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


# ── domain↔ORM mapping ──────────────────────────────────────────────────────


def _entitlement_to_domain(orm: PlanEntitlementORM) -> PlanEntitlement:
    return PlanEntitlement(
        id=orm.id,
        plan_id=orm.plan_id,
        class_id=orm.class_id,
        quantity=orm.quantity,
        reset_period=ResetPeriod(orm.reset_period),
        created_at=orm.created_at,
    )


def _plan_to_domain(orm: MembershipPlanORM) -> MembershipPlan:
    return MembershipPlan(
        id=orm.id,
        tenant_id=orm.tenant_id,
        name=orm.name,
        description=orm.description,
        type=PlanType(orm.type),
        price_cents=orm.price_cents,
        currency=orm.currency,
        billing_period=BillingPeriod(orm.billing_period),
        duration_days=orm.duration_days,
        is_active=orm.is_active,
        custom_attrs=orm.custom_attrs or {},
        entitlements=[_entitlement_to_domain(e) for e in orm.entitlements],
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


# ── input shape for create/update ──────────────────────────────────────────


class EntitlementInput:
    """Plain input shape for creating/replacing an entitlement.

    Intentionally not a BaseModel — the service validates shape before
    handing off, and the repo's job is just persistence.
    """

    def __init__(
        self,
        *,
        class_id: UUID | None,
        quantity: int | None,
        reset_period: ResetPeriod,
    ) -> None:
        self.class_id = class_id
        self.quantity = quantity
        self.reset_period = reset_period


# ── repository ─────────────────────────────────────────────────────────────


class MembershipPlanRepository:
    """CRUD for membership_plans + plan_entitlements. No transactions owned."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        name: str,
        type: PlanType,
        price_cents: int,
        currency: str,
        billing_period: BillingPeriod,
        duration_days: int | None = None,
        description: str | None = None,
        is_active: bool = True,
        custom_attrs: dict[str, Any] | None = None,
        entitlements: list[EntitlementInput] | None = None,
    ) -> MembershipPlan:
        """Insert a new plan + any entitlement rows in one transaction.

        Raises:
            MembershipPlanAlreadyExistsError: duplicate (tenant_id, name).
        """
        orm = MembershipPlanORM(
            tenant_id=tenant_id,
            name=name,
            description=description,
            type=type.value,
            price_cents=price_cents,
            currency=currency,
            billing_period=billing_period.value,
            duration_days=duration_days,
            is_active=is_active,
            custom_attrs=custom_attrs or {},
            entitlements=[
                PlanEntitlementORM(
                    class_id=e.class_id,
                    quantity=e.quantity,
                    reset_period=e.reset_period.value,
                )
                for e in (entitlements or [])
            ],
        )
        self._session.add(orm)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise MembershipPlanAlreadyExistsError(name) from exc

        # Re-fetch with eager entitlements for the return shape
        return await self._fetch_with_entitlements(orm.id)

    async def find_by_id(self, plan_id: UUID) -> MembershipPlan | None:
        """Look up by primary key, eager-loading entitlements."""
        result = await self._session.execute(
            select(MembershipPlanORM)
            .options(selectinload(MembershipPlanORM.entitlements))
            .where(MembershipPlanORM.id == plan_id)
        )
        orm = result.scalar_one_or_none()
        return _plan_to_domain(orm) if orm else None

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MembershipPlan]:
        """List plans in one tenant. Defaults to active only.

        Entitlements are eager-loaded so the frontend list can show
        what each plan grants without N+1 queries.
        """
        stmt = (
            select(MembershipPlanORM)
            .options(selectinload(MembershipPlanORM.entitlements))
            .where(MembershipPlanORM.tenant_id == tenant_id)
        )
        if not include_inactive:
            stmt = stmt.where(MembershipPlanORM.is_active.is_(True))
        stmt = stmt.order_by(MembershipPlanORM.name.asc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_plan_to_domain(orm) for orm in result.scalars()]

    async def count_for_tenant(self, tenant_id: UUID, *, include_inactive: bool = False) -> int:
        """Count plans for a tenant (dashboard widget)."""
        stmt = select(func.count(MembershipPlanORM.id)).where(
            MembershipPlanORM.tenant_id == tenant_id
        )
        if not include_inactive:
            stmt = stmt.where(MembershipPlanORM.is_active.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(
        self,
        plan_id: UUID,
        *,
        entitlements: list[EntitlementInput] | None = None,
        **fields: Any,
    ) -> MembershipPlan:
        """Update plan fields. If ``entitlements`` is provided, REPLACES
        the existing rows entirely (delete + insert in the same transaction).

        Raises:
            MembershipPlanNotFoundError: no plan matches plan_id.
            MembershipPlanAlreadyExistsError: rename collides within tenant.
        """
        # Scalar field update (skip if nothing to change)
        if fields:
            try:
                await self._session.execute(
                    update(MembershipPlanORM)
                    .where(MembershipPlanORM.id == plan_id)
                    .values(**fields)
                )
                await self._session.flush()
            except IntegrityError as exc:
                await self._session.rollback()
                raise MembershipPlanAlreadyExistsError(str(fields.get("name", ""))) from exc

        # Replace entitlements via the ORM relationship (cascade=delete-orphan
        # on the collection handles the deletes atomically, and adding to the
        # relationship keeps the session cache in sync — bulk-delete + add
        # bypasses the identity map and returns stale data on re-fetch).
        if entitlements is not None:
            result = await self._session.execute(
                select(MembershipPlanORM)
                .options(selectinload(MembershipPlanORM.entitlements))
                .where(MembershipPlanORM.id == plan_id)
            )
            plan_orm = result.scalar_one_or_none()
            if plan_orm is None:
                raise MembershipPlanNotFoundError(str(plan_id))
            plan_orm.entitlements.clear()
            for e in entitlements:
                plan_orm.entitlements.append(
                    PlanEntitlementORM(
                        class_id=e.class_id,
                        quantity=e.quantity,
                        reset_period=e.reset_period.value,
                    )
                )
            await self._session.flush()

        plan = await self._fetch_with_entitlements(plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(str(plan_id))
        return plan

    async def _fetch_with_entitlements(self, plan_id: UUID) -> MembershipPlan | None:
        """Re-fetch a plan + entitlements after a mutation."""
        result = await self._session.execute(
            select(MembershipPlanORM)
            .options(selectinload(MembershipPlanORM.entitlements))
            .where(MembershipPlanORM.id == plan_id)
        )
        orm = result.scalar_one_or_none()
        return _plan_to_domain(orm) if orm else None
