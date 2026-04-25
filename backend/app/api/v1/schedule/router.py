"""Schedule routes — ``/api/v1/schedule``.

Thin Layer 1 — validates HTTP input, calls ScheduleService, formats
response. All business logic (tenant scoping, feature flag, role gate,
materialization, re-materialization, bulk atomicity) lives in the
service.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.schedule.schemas import (
    BulkActionRequest,
    BulkActionResponse,
    CancelSessionRequest,
    CreateAdHocSessionRequest,
    CreateTemplateRequest,
    SessionResponse,
    TemplateResponse,
    UpdateSessionRequest,
    UpdateTemplateRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.class_schedule_template import ClassScheduleTemplate
from app.domain.entities.class_session import ClassSession
from app.services.schedule_service import ScheduleService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> ScheduleService:
    return ScheduleService(session)


def _to_template_response(t: ClassScheduleTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        tenant_id=t.tenant_id,
        class_id=t.class_id,
        weekdays=t.weekdays,
        start_time=t.start_time,
        end_time=t.end_time,
        head_coach_id=t.head_coach_id,
        assistant_coach_id=t.assistant_coach_id,
        starts_on=t.starts_on,
        ends_on=t.ends_on,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _to_session_response(s: ClassSession) -> SessionResponse:
    return SessionResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        class_id=s.class_id,
        template_id=s.template_id,
        starts_at=s.starts_at,
        ends_at=s.ends_at,
        head_coach_id=s.head_coach_id,
        assistant_coach_id=s.assistant_coach_id,
        status=s.status,
        is_customized=s.is_customized,
        cancelled_at=s.cancelled_at,
        cancelled_by=s.cancelled_by,
        cancellation_reason=s.cancellation_reason,
        notes=s.notes,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


# ── Templates ─────────────────────────────────────────────────────────


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a template + auto-materialize 8 weeks of sessions",
)
async def create_template(
    body: CreateTemplateRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> TemplateResponse:
    t = await service.create_template(
        caller=caller,
        class_id=body.class_id,
        weekdays=body.weekdays,
        start_time=body.start_time,
        end_time=body.end_time,
        head_coach_id=body.head_coach_id,
        assistant_coach_id=body.assistant_coach_id,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )
    return _to_template_response(t)


@router.get(
    "/templates",
    response_model=list[TemplateResponse],
    summary="List templates in the caller's tenant",
)
async def list_templates(
    class_id: UUID | None = Query(default=None),
    only_active: bool = Query(default=False),
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> list[TemplateResponse]:
    rows = await service.list_templates(
        caller=caller, class_id=class_id, only_active=only_active
    )
    return [_to_template_response(t) for t in rows]


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
)
async def get_template(
    template_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> TemplateResponse:
    return _to_template_response(
        await service.get_template(caller=caller, template_id=template_id)
    )


@router.patch(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Edit a template — triggers re-materialization (owner+)",
)
async def update_template(
    template_id: UUID,
    body: UpdateTemplateRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> TemplateResponse:
    fields = body.model_dump(exclude_unset=True)
    updated = await service.update_template(
        caller=caller, template_id=template_id, **fields
    )
    return _to_template_response(updated)


@router.delete(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Deactivate + cancel future non-customized sessions (owner+)",
)
async def deactivate_template(
    template_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> TemplateResponse:
    t = await service.deactivate_template(caller=caller, template_id=template_id)
    return _to_template_response(t)


# ── Sessions ──────────────────────────────────────────────────────────


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an ad-hoc session (owner+)",
)
async def create_session(
    body: CreateAdHocSessionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> SessionResponse:
    s = await service.create_adhoc_session(
        caller=caller,
        class_id=body.class_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        head_coach_id=body.head_coach_id,
        assistant_coach_id=body.assistant_coach_id,
        notes=body.notes,
    )
    return _to_session_response(s)


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="Calendar range query",
)
async def list_sessions(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    class_id: UUID | None = Query(default=None),
    coach_id: UUID | None = Query(default=None),
    include_cancelled: bool = Query(default=True),
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> list[SessionResponse]:
    rows = await service.list_sessions(
        caller=caller,
        from_=from_,
        to=to,
        class_id=class_id,
        coach_id=coach_id,
        include_cancelled=include_cancelled,
    )
    return [_to_session_response(s) for s in rows]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
)
async def get_session_endpoint(
    session_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> SessionResponse:
    return _to_session_response(
        await service.get_session(caller=caller, session_id=session_id)
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Edit a session — swap coach, shift time, add notes (owner+)",
)
async def update_session(
    session_id: UUID,
    body: UpdateSessionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> SessionResponse:
    updated = await service.update_session(
        caller=caller,
        session_id=session_id,
        head_coach_id=body.head_coach_id,
        assistant_coach_id=body.assistant_coach_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        notes=body.notes,
    )
    return _to_session_response(updated)


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=SessionResponse,
    summary="Cancel a session (owner+)",
)
async def cancel_session(
    session_id: UUID,
    body: CancelSessionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> SessionResponse:
    s = await service.cancel_session(
        caller=caller, session_id=session_id, reason=body.reason
    )
    return _to_session_response(s)


# ── Bulk action ──────────────────────────────────────────────────────


@router.post(
    "/bulk-action",
    response_model=BulkActionResponse,
    summary="Cancel / swap coach for every session in a date range (owner+)",
)
async def bulk_action(
    body: BulkActionRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: ScheduleService = Depends(_get_service),
) -> BulkActionResponse:
    result = await service.bulk_action(
        caller=caller,
        class_id=body.class_id,
        from_date=body.from_date,
        to_date=body.to_date,
        action=body.action,
        new_coach_id=body.new_coach_id,
        reason=body.reason,
        substitute_pay_model=body.substitute_pay_model,
        substitute_pay_amount_cents=body.substitute_pay_amount_cents,
    )
    return BulkActionResponse(
        action=result.action,
        affected_ids=result.affected_ids,
        cancelled_count=result.cancelled_count,
        swapped_count=result.swapped_count,
        substitute_link_id=result.substitute_link_id,
    )
