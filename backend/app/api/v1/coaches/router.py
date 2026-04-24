"""Coaches routes — ``/api/v1/coaches``, ``/api/v1/class-coaches``.

Thin Layer 1 — all business logic (tenant scoping, role gates, payroll
math) lives in the service. Routes parse HTTP input, call the service,
format the response.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.coaches.schemas import (
    ClassCoachResponse,
    CoachResponse,
    CreateCoachRequest,
    EarningsBreakdownResponse,
    EarningsLinkRowResponse,
    InviteCoachUserRequest,
    UpdateClassCoachRequest,
    UpdateCoachRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.class_coach import ClassCoach
from app.domain.entities.coach import Coach, CoachStatus
from app.services.coach_service import CoachService, EarningsBreakdown

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Two routers in this module — one for coaches, one for the link row
# under ``/class-coaches/{id}``. They share the dependency helper.
coaches_router = APIRouter()
class_coaches_router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> CoachService:
    return CoachService(session)


def _to_coach_response(c: Coach) -> CoachResponse:
    return CoachResponse(
        id=c.id,
        tenant_id=c.tenant_id,
        user_id=c.user_id,
        first_name=c.first_name,
        last_name=c.last_name,
        phone=c.phone,
        email=c.email,
        hired_at=c.hired_at,
        status=c.status,
        frozen_at=c.frozen_at,
        cancelled_at=c.cancelled_at,
        custom_attrs=c.custom_attrs,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_link_response(link: ClassCoach) -> ClassCoachResponse:
    return ClassCoachResponse(
        id=link.id,
        tenant_id=link.tenant_id,
        class_id=link.class_id,
        coach_id=link.coach_id,
        role=link.role,
        is_primary=link.is_primary,
        pay_model=link.pay_model,
        pay_amount_cents=link.pay_amount_cents,
        weekdays=link.weekdays,
        starts_on=link.starts_on,
        ends_on=link.ends_on,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _to_earnings_response(bd: EarningsBreakdown) -> EarningsBreakdownResponse:
    return EarningsBreakdownResponse.model_validate(
        {
            "coach_id": bd.coach_id,
            "from": bd.from_,
            "to": bd.to,
            "effective_from": bd.effective_from,
            "effective_to": bd.effective_to,
            "currency": bd.currency,
            "total_cents": bd.total_cents,
            "by_link": [
                EarningsLinkRowResponse(
                    class_id=r.class_id,
                    class_name=r.class_name,
                    role=r.role,
                    pay_model=r.pay_model,
                    pay_amount_cents=r.pay_amount_cents,
                    cents=r.cents,
                    unit_count=r.unit_count,
                )
                for r in bd.by_link
            ],
            "by_class_cents": bd.by_class_cents,
            "by_pay_model_cents": bd.by_pay_model_cents,
        }
    )


# ── Coach CRUD ────────────────────────────────────────────────────────


@coaches_router.post(
    "",
    response_model=CoachResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a coach",
)
async def create_coach(
    body: CreateCoachRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    coach = await service.create_coach(
        caller=caller,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        email=body.email,
        user_id=body.user_id,
        hired_at=body.hired_at,
        custom_attrs=body.custom_attrs,
    )
    return _to_coach_response(coach)


@coaches_router.get(
    "",
    response_model=list[CoachResponse],
    summary="List coaches in the caller's tenant",
)
async def list_coaches(
    status_filter: list[CoachStatus] | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> list[CoachResponse]:
    coaches = await service.list_coaches(
        caller=caller, status=status_filter, search=search, limit=limit, offset=offset
    )
    return [_to_coach_response(c) for c in coaches]


@coaches_router.get(
    "/{coach_id}",
    response_model=CoachResponse,
    summary="Fetch a single coach",
)
async def get_coach(
    coach_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    return _to_coach_response(await service.get_coach(caller=caller, coach_id=coach_id))


@coaches_router.patch(
    "/{coach_id}",
    response_model=CoachResponse,
    summary="Update coach fields (owner+)",
)
async def update_coach(
    coach_id: UUID,
    body: UpdateCoachRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    fields = body.model_dump(exclude_unset=True)
    updated = await service.update_coach(caller=caller, coach_id=coach_id, **fields)
    return _to_coach_response(updated)


@coaches_router.post(
    "/{coach_id}/freeze",
    response_model=CoachResponse,
    summary="Freeze a coach (owner+)",
)
async def freeze_coach(
    coach_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    return _to_coach_response(await service.freeze_coach(caller=caller, coach_id=coach_id))


@coaches_router.post(
    "/{coach_id}/unfreeze",
    response_model=CoachResponse,
    summary="Unfreeze a coach (owner+)",
)
async def unfreeze_coach(
    coach_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    return _to_coach_response(
        await service.unfreeze_coach(caller=caller, coach_id=coach_id)
    )


@coaches_router.post(
    "/{coach_id}/cancel",
    response_model=CoachResponse,
    summary="Cancel a coach — terminal (owner+)",
)
async def cancel_coach(
    coach_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    return _to_coach_response(await service.cancel_coach(caller=caller, coach_id=coach_id))


@coaches_router.post(
    "/{coach_id}/invite-user",
    response_model=CoachResponse,
    summary="Create a login for the coach (owner+)",
)
async def invite_user(
    coach_id: UUID,
    body: InviteCoachUserRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> CoachResponse:
    updated = await service.invite_user(
        caller=caller, coach_id=coach_id, email=body.email, password=body.password
    )
    return _to_coach_response(updated)


@coaches_router.get(
    "/{coach_id}/classes",
    response_model=list[ClassCoachResponse],
    summary="List classes this coach teaches",
)
async def list_classes_for_coach(
    coach_id: UUID,
    only_current: bool = Query(default=False),
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> list[ClassCoachResponse]:
    links = await service.list_classes_for_coach(
        caller=caller, coach_id=coach_id, only_current=only_current
    )
    return [_to_link_response(link) for link in links]


@coaches_router.get(
    "/{coach_id}/earnings",
    response_model=EarningsBreakdownResponse,
    summary="Payroll estimate for a coach over a date range",
)
async def coach_earnings(
    coach_id: UUID,
    from_: date = Query(alias="from"),
    to: date = Query(),
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> EarningsBreakdownResponse:
    bd = await service.earnings_for(
        caller=caller, coach_id=coach_id, from_=from_, to=to
    )
    return _to_earnings_response(bd)


@coaches_router.get(
    "/earnings/summary",
    response_model=list[EarningsBreakdownResponse],
    summary="Earnings across all coaches (owner+)",
)
async def earnings_summary(
    from_: date = Query(alias="from"),
    to: date = Query(),
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> list[EarningsBreakdownResponse]:
    results = await service.earnings_summary(caller=caller, from_=from_, to=to)
    return [_to_earnings_response(r) for r in results]


# ── Class ↔ Coach link (PATCH / DELETE on /class-coaches/{id}) ────────
# Class-side endpoints (POST /classes/{class_id}/coaches,
# GET /classes/{class_id}/coaches) live on the classes router — they
# read naturally as "coaches of this class". See classes/router.py.


@class_coaches_router.patch(
    "/{link_id}",
    response_model=ClassCoachResponse,
    summary="Edit a class-coach link (owner+)",
)
async def update_link(
    link_id: UUID,
    body: UpdateClassCoachRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> ClassCoachResponse:
    fields = body.model_dump(exclude_unset=True)
    updated = await service.update_link(caller=caller, link_id=link_id, **fields)
    return _to_link_response(updated)


@class_coaches_router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a class-coach link (owner+)",
)
async def delete_link(
    link_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: CoachService = Depends(_get_service),
) -> None:
    await service.remove_link(caller=caller, link_id=link_id)
