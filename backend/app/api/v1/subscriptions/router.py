"""Subscriptions routes — ``/api/v1/subscriptions`` + one member-nested route.

Thin Layer 1. Validates HTTP input, calls SubscriptionService, formats
output. All business logic (tenant scoping, role gates, state-machine
validation, price lock, Member.status sync) lives in the service.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.subscriptions.schemas import (
    CancelSubscriptionRequest,
    ChangePlanRequest,
    CreateSubscriptionRequest,
    FreezeSubscriptionRequest,
    RenewSubscriptionRequest,
    SubscriptionEventResponse,
    SubscriptionResponse,
)
from app.core.security import TokenPayload
from app.domain.entities.subscription import (
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from app.services.subscription_service import SubscriptionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> SubscriptionService:
    return SubscriptionService(session)


def _sub_to_response(s: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        member_id=s.member_id,
        plan_id=s.plan_id,
        status=s.status,
        price_cents=s.price_cents,
        currency=s.currency,
        payment_method=s.payment_method,
        payment_method_detail=s.payment_method_detail,
        started_at=s.started_at,
        expires_at=s.expires_at,
        frozen_at=s.frozen_at,
        frozen_until=s.frozen_until,
        expired_at=s.expired_at,
        cancelled_at=s.cancelled_at,
        cancellation_reason=s.cancellation_reason,
        replaced_at=s.replaced_at,
        replaced_by_id=s.replaced_by_id,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _event_to_response(e: SubscriptionEvent) -> SubscriptionEventResponse:
    return SubscriptionEventResponse(
        id=e.id,
        tenant_id=e.tenant_id,
        subscription_id=e.subscription_id,
        event_type=e.event_type,
        event_data=e.event_data,
        occurred_at=e.occurred_at,
        created_by=e.created_by,
    )


# ── Commands ─────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a member in a plan",
    description=(
        "staff+. Creates an active subscription with the plan's current price "
        "snapshotted. Fails 409 if the member already has a live sub."
    ),
)
async def create_subscription(
    body: CreateSubscriptionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.create(
        caller=caller,
        member_id=body.member_id,
        plan_id=body.plan_id,
        started_at=body.started_at,
        expires_at=body.expires_at,
        payment_method=body.payment_method,
        payment_method_detail=body.payment_method_detail,
    )
    return _sub_to_response(sub)


@router.post(
    "/{sub_id}/freeze",
    response_model=SubscriptionResponse,
    summary="Freeze a subscription",
    description=(
        "staff+. Optional ``frozen_until`` for auto-unfreeze. Paused time "
        "extends expires_at on unfreeze."
    ),
)
async def freeze_subscription(
    sub_id: UUID,
    body: FreezeSubscriptionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.freeze(caller=caller, sub_id=sub_id, frozen_until=body.frozen_until)
    return _sub_to_response(sub)


@router.post(
    "/{sub_id}/unfreeze",
    response_model=SubscriptionResponse,
    summary="Unfreeze a subscription",
    description="staff+. Extends expires_at by the frozen duration.",
)
async def unfreeze_subscription(
    sub_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.unfreeze(caller=caller, sub_id=sub_id)
    return _sub_to_response(sub)


@router.post(
    "/{sub_id}/renew",
    response_model=SubscriptionResponse,
    summary="Renew a subscription (extend expires_at)",
    description=(
        "staff+. Default extension = plan's billing period. Works on "
        "`active` (extend ahead) and `expired` (rescue a late member — "
        "same row, fresh expires_at, `days_late` logged)."
    ),
)
async def renew_subscription(
    sub_id: UUID,
    body: RenewSubscriptionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.renew(
        caller=caller,
        sub_id=sub_id,
        new_expires_at=body.new_expires_at,
        new_payment_method=body.new_payment_method,
        new_payment_method_detail=body.new_payment_method_detail,
    )
    return _sub_to_response(sub)


@router.post(
    "/{sub_id}/change-plan",
    response_model=SubscriptionResponse,
    summary="Switch the member to a different plan",
    description=(
        "staff+. Old sub → `replaced` (NOT cancelled — different for reports). "
        "New sub is active with a fresh price snapshot from the new plan. "
        "Atomic: both rows land or neither does. Returns the NEW sub."
    ),
)
async def change_plan(
    sub_id: UUID,
    body: ChangePlanRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.change_plan(
        caller=caller,
        sub_id=sub_id,
        new_plan_id=body.new_plan_id,
        effective_date=body.effective_date,
    )
    return _sub_to_response(sub)


@router.post(
    "/{sub_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription (hard-terminal)",
    description=(
        "staff+. Member actively left. Optional reason + detail for churn "
        "analytics. Rejoin = new sub (this one stays as history)."
    ),
)
async def cancel_subscription(
    sub_id: UUID,
    body: CancelSubscriptionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.cancel(caller=caller, sub_id=sub_id, reason=body.reason, detail=body.detail)
    return _sub_to_response(sub)


# ── Queries ──────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[SubscriptionResponse],
    summary="List subscriptions in the caller's tenant",
    description=(
        "Filterable: ``member_id``, ``status``, ``plan_id``, ``expires_before``, "
        "``expires_within_days`` (the 'about to expire' dashboard query)."
    ),
)
async def list_subscriptions(
    member_id: UUID | None = Query(default=None),
    status_filter: SubscriptionStatus | None = Query(default=None, alias="status"),
    plan_id: UUID | None = Query(default=None),
    expires_before: date | None = Query(default=None),
    expires_within_days: int | None = Query(default=None, ge=0, le=365),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> list[SubscriptionResponse]:
    subs = await service.list_for_tenant(
        caller=caller,
        member_id=member_id,
        status=status_filter,
        plan_id=plan_id,
        expires_before=expires_before,
        expires_within_days=expires_within_days,
        limit=limit,
        offset=offset,
    )
    return [_sub_to_response(s) for s in subs]


@router.get(
    "/{sub_id}",
    response_model=SubscriptionResponse,
    summary="Get a subscription by ID",
)
async def get_subscription(
    sub_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> SubscriptionResponse:
    sub = await service.get(caller=caller, sub_id=sub_id)
    return _sub_to_response(sub)


@router.get(
    "/{sub_id}/events",
    response_model=list[SubscriptionEventResponse],
    summary="Get the timeline of events for a subscription",
    description=(
        "All state transitions for this sub, newest first. The member detail "
        "page renders this as a human-readable timeline. System events "
        "(nightly auto-unfreeze / auto-expire) have ``created_by = null``."
    ),
)
async def list_subscription_events(
    sub_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: SubscriptionService = Depends(_get_service),
) -> list[SubscriptionEventResponse]:
    events = await service.list_events(caller=caller, sub_id=sub_id)
    return [_event_to_response(e) for e in events]
