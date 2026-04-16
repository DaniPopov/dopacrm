"""Membership plan service — orchestrates plan CRUD + entitlement rules.

Layer 2. Business rules live here:

- Tenant scoping on every method. super_admin bypasses reads but is
  rejected for mutations (commercial decisions are gym-operator work).
- Owner-only for create / update / deactivate / activate. Staff and
  sales can READ the catalog (they need it to enroll members into
  plans when Subscriptions lands).
- Entitlement validation: if a rule references a class_id, that class
  must belong to the same tenant. Cross-tenant class references are
  blocked at this layer before the DB's FK check (which would fire
  with a generic IntegrityError instead of a specific AppError).
- Shape validation: one_time vs recurring, duration_days presence,
  entitlement quantity vs reset_period — redundant with DB check
  constraints but gives a nicer error code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    EntitlementInput,
    MembershipPlanRepository,
)
from app.domain.entities.membership_plan import (
    BillingPeriod,
    MembershipPlan,
    PlanType,
    ResetPeriod,
)
from app.domain.entities.user import Role
from app.domain.exceptions import (
    InsufficientPermissionsError,
    InvalidPlanShapeError,
    MembershipPlanNotFoundError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload


class MembershipPlanService:
    """Plan catalog CRUD + entitlement orchestration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MembershipPlanRepository(session)
        self._class_repo = GymClassRepository(session)

    # ── Commands (owner-only) ────────────────────────────────────────────────

    async def create(
        self,
        *,
        caller: TokenPayload,
        name: str,
        type: PlanType,
        price_cents: int,
        billing_period: BillingPeriod,
        duration_days: int | None = None,
        currency: str = "ILS",
        description: str | None = None,
        custom_attrs: dict[str, Any] | None = None,
        entitlements: list[EntitlementInput] | None = None,
    ) -> MembershipPlan:
        """Create a plan + its entitlement rules.

        Validates shape and cross-tenant class references before the DB
        sees the rows — returns PLAN_INVALID_SHAPE (422) rather than a
        generic IntegrityError.
        """
        tenant_id = self._require_owner_in_tenant(caller)
        self._validate_plan_shape(type, billing_period, duration_days)
        await self._validate_entitlements(tenant_id, entitlements or [])

        plan = await self._repo.create(
            tenant_id=tenant_id,
            name=name,
            type=type,
            price_cents=price_cents,
            currency=currency,
            billing_period=billing_period,
            duration_days=duration_days,
            description=description,
            custom_attrs=custom_attrs,
            entitlements=entitlements or [],
        )
        await self._session.commit()
        return plan

    async def update(
        self,
        *,
        caller: TokenPayload,
        plan_id: UUID,
        entitlements: list[EntitlementInput] | None = None,
        **fields: Any,
    ) -> MembershipPlan:
        """Partial update. If ``entitlements`` is provided, replaces the
        full list. To leave entitlements alone, omit the argument.

        Shape-validates the resulting plan (using updated fields where
        provided, existing values where not).
        """
        self._require_owner(caller)
        existing = await self._get_in_tenant(caller, plan_id)

        # Validate shape with the merged view (old + new fields)
        new_type = PlanType(fields["type"]) if "type" in fields else existing.type
        new_billing = (
            BillingPeriod(fields["billing_period"])
            if "billing_period" in fields
            else existing.billing_period
        )
        new_duration = fields.get("duration_days", existing.duration_days)
        self._validate_plan_shape(new_type, new_billing, new_duration)

        if entitlements is not None:
            await self._validate_entitlements(existing.tenant_id, entitlements)

        updated = await self._repo.update(plan_id, entitlements=entitlements, **fields)
        await self._session.commit()
        return updated

    async def deactivate(self, *, caller: TokenPayload, plan_id: UUID) -> MembershipPlan:
        """Soft-disable. Existing subscriptions keep their price lock;
        new subscriptions can't reference this plan (enforced when
        Subscriptions lands)."""
        self._require_owner(caller)
        await self._get_in_tenant(caller, plan_id)
        updated = await self._repo.update(plan_id, is_active=False)
        await self._session.commit()
        return updated

    async def activate(self, *, caller: TokenPayload, plan_id: UUID) -> MembershipPlan:
        """Re-enable a deactivated plan."""
        self._require_owner(caller)
        await self._get_in_tenant(caller, plan_id)
        updated = await self._repo.update(plan_id, is_active=True)
        await self._session.commit()
        return updated

    # ── Queries (any tenant user) ────────────────────────────────────────────

    async def get(self, *, caller: TokenPayload, plan_id: UUID) -> MembershipPlan:
        """Fetch one plan. Tenant-scoped: 404 for cross-tenant plans."""
        return await self._get_in_tenant(caller, plan_id)

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MembershipPlan]:
        """List plans in the caller's tenant. Any tenant user can read."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.list_for_tenant(
            tenant_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )

    async def count_for_tenant(
        self, *, caller: TokenPayload, include_inactive: bool = False
    ) -> int:
        """Count plans in the caller's tenant."""
        tenant_id = self._require_tenant(caller)
        return await self._repo.count_for_tenant(tenant_id, include_inactive=include_inactive)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_in_tenant(self, caller: TokenPayload, plan_id: UUID) -> MembershipPlan:
        """Fetch + verify tenant match, or raise MembershipPlanNotFoundError.

        super_admin bypasses scoping (platform support). Tenant users see
        only their own gym's plans; other-tenant lookup returns 404,
        not 403 (no existence leak).
        """
        plan = await self._repo.find_by_id(plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(str(plan_id))
        if caller.role == Role.SUPER_ADMIN.value:
            return plan
        if caller.tenant_id is None or str(plan.tenant_id) != str(caller.tenant_id):
            raise MembershipPlanNotFoundError(str(plan_id))
        return plan

    @staticmethod
    def _validate_plan_shape(
        type: PlanType,
        billing_period: BillingPeriod,
        duration_days: int | None,
    ) -> None:
        """Shape rules mirror the DB check constraint — but we raise the
        typed error here so the API returns a useful 422 message."""
        if type == PlanType.RECURRING:
            if duration_days is not None:
                raise InvalidPlanShapeError("recurring plans must not set duration_days")
            if billing_period == BillingPeriod.ONE_TIME:
                raise InvalidPlanShapeError("recurring plans need a recurring billing_period")
        else:  # ONE_TIME
            if duration_days is None:
                raise InvalidPlanShapeError("one_time plans require duration_days")
            if billing_period != BillingPeriod.ONE_TIME:
                raise InvalidPlanShapeError("one_time plans must use billing_period='one_time'")

    async def _validate_entitlements(
        self, tenant_id: UUID, entitlements: list[EntitlementInput]
    ) -> None:
        """Shape + tenant-scope the class_ids referenced by entitlements."""
        for e in entitlements:
            if e.reset_period == ResetPeriod.UNLIMITED and e.quantity is not None:
                raise InvalidPlanShapeError("unlimited entitlements must not set quantity")
            if e.reset_period != ResetPeriod.UNLIMITED and e.quantity is None:
                raise InvalidPlanShapeError("metered entitlements require quantity")
            if e.quantity is not None and e.quantity <= 0:
                raise InvalidPlanShapeError("entitlement quantity must be > 0")
            if e.class_id is not None:
                cls = await self._class_repo.find_by_id(e.class_id)
                if cls is None or str(cls.tenant_id) != str(tenant_id):
                    raise InvalidPlanShapeError(
                        f"class_id {e.class_id} does not belong to this tenant"
                    )

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> UUID:
        """Return caller's tenant_id or raise. super_admin rejected."""
        from uuid import UUID as _UUID

        if caller.role == Role.SUPER_ADMIN.value or caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_owner(caller: TokenPayload) -> None:
        """Mutations are owner-only (+ super_admin for platform support)."""
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()

    def _require_owner_in_tenant(self, caller: TokenPayload) -> UUID:
        self._require_owner(caller)
        return self._require_tenant(caller)
