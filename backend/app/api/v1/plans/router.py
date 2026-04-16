"""Membership Plans routes — ``/api/v1/plans``.

Thin layer. Validates HTTP input, calls MembershipPlanService, formats
HTTP output. All business logic (tenant scoping, role gating, shape
validation, cross-tenant class_id checks) lives in the service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.adapters.storage.postgres.membership_plan.repositories import (
    EntitlementInput,
)
from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.plans.schemas import (
    CreatePlanRequest,
    EntitlementInputSchema,
    EntitlementResponseSchema,
    PlanResponse,
    UpdatePlanRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.membership_plan import MembershipPlan, PlanEntitlement
from app.services.membership_plan_service import MembershipPlanService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> MembershipPlanService:
    return MembershipPlanService(session)


def _entitlement_to_response(e: PlanEntitlement) -> EntitlementResponseSchema:
    return EntitlementResponseSchema(
        id=e.id,
        plan_id=e.plan_id,
        class_id=e.class_id,
        quantity=e.quantity,
        reset_period=e.reset_period,
        created_at=e.created_at,
    )


def _plan_to_response(plan: MembershipPlan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        tenant_id=plan.tenant_id,
        name=plan.name,
        description=plan.description,
        type=plan.type,
        price_cents=plan.price_cents,
        currency=plan.currency,
        billing_period=plan.billing_period,
        duration_days=plan.duration_days,
        is_active=plan.is_active,
        custom_attrs=plan.custom_attrs,
        entitlements=[_entitlement_to_response(e) for e in plan.entitlements],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _schema_to_domain(e: EntitlementInputSchema) -> EntitlementInput:
    """Convert HTTP input shape into the repo's plain-object input."""
    return EntitlementInput(
        class_id=e.class_id,
        quantity=e.quantity,
        reset_period=e.reset_period,
    )


@router.post(
    "",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a membership plan",
    description=(
        "Owner-only. Creates a plan + its entitlement rules atomically. "
        "Shape is validated (one_time vs recurring, entitlement quantity "
        "vs reset_period) before the DB sees it."
    ),
)
async def create_plan(
    body: CreatePlanRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> PlanResponse:
    plan = await service.create(
        caller=caller,
        name=body.name,
        description=body.description,
        type=body.type,
        price_cents=body.price_cents,
        currency=body.currency,
        billing_period=body.billing_period,
        duration_days=body.duration_days,
        custom_attrs=body.custom_attrs,
        entitlements=[_schema_to_domain(e) for e in body.entitlements],
    )
    return _plan_to_response(plan)


@router.get(
    "",
    response_model=list[PlanResponse],
    summary="List membership plans",
    description=(
        "Lists plans in the caller's tenant (any tenant user can read). "
        "Entitlements are eager-loaded. Use ``include_inactive=true`` to "
        "see deactivated plans."
    ),
)
async def list_plans(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> list[PlanResponse]:
    plans = await service.list_for_tenant(
        caller=caller,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return [_plan_to_response(p) for p in plans]


@router.get(
    "/{plan_id}",
    response_model=PlanResponse,
    summary="Get a plan by ID",
)
async def get_plan(
    plan_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> PlanResponse:
    plan = await service.get(caller=caller, plan_id=plan_id)
    return _plan_to_response(plan)


@router.patch(
    "/{plan_id}",
    response_model=PlanResponse,
    summary="Update a plan (partial)",
    description=(
        "Owner-only. Omit ``entitlements`` to leave them alone; pass "
        "``[]`` to clear all rules; pass a list to REPLACE the full set. "
        "Shape re-validated on update."
    ),
)
async def update_plan(
    plan_id: UUID,
    body: UpdatePlanRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> PlanResponse:
    payload = body.model_dump(exclude_unset=True)
    entitlements_raw = payload.pop("entitlements", None)
    entitlements = (
        [_schema_to_domain(EntitlementInputSchema(**e)) for e in entitlements_raw]
        if entitlements_raw is not None
        else None
    )
    plan = await service.update(
        caller=caller, plan_id=plan_id, entitlements=entitlements, **payload
    )
    return _plan_to_response(plan)


@router.post(
    "/{plan_id}/deactivate",
    response_model=PlanResponse,
    summary="Deactivate a plan (soft)",
    description=(
        "Owner-only. Existing subscriptions keep working; new ones can't reference this plan."
    ),
)
async def deactivate_plan(
    plan_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> PlanResponse:
    plan = await service.deactivate(caller=caller, plan_id=plan_id)
    return _plan_to_response(plan)


@router.post(
    "/{plan_id}/activate",
    response_model=PlanResponse,
    summary="Re-activate a deactivated plan",
    description="Owner-only.",
)
async def activate_plan(
    plan_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MembershipPlanService = Depends(_get_service),
) -> PlanResponse:
    plan = await service.activate(caller=caller, plan_id=plan_id)
    return _plan_to_response(plan)
