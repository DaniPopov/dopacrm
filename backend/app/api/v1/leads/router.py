"""Leads routes — ``/api/v1/leads``.

Thin Layer 1. All business logic (feature gate, role gates, state
machine, atomic convert) lives in ``LeadService``. Routes parse HTTP
input, call the service, format the response.

Endpoint table mirrors ``docs/features/leads.md`` §"API Endpoints".
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.leads.schemas import (
    AddActivityRequest,
    AssignLeadRequest,
    ConvertedMemberSummary,
    ConvertedSubscriptionSummary,
    ConvertLeadRequest,
    ConvertLeadResponse,
    CreateLeadRequest,
    LeadActivityResponse,
    LeadResponse,
    LeadStatsResponse,
    LostReasonRowResponse,
    SetStatusRequest,
    UpdateLeadRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.lead import Lead, LeadSource, LeadStatus
from app.domain.entities.lead_activity import LeadActivity
from app.domain.entities.member import Member
from app.domain.entities.subscription import Subscription
from app.services.lead_service import ConvertResult, LeadService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> LeadService:
    return LeadService(session)


# ── Conversion helpers (entity → response) ────────────────────────────


def _to_lead_response(lead: Lead) -> LeadResponse:
    return LeadResponse(
        id=lead.id,
        tenant_id=lead.tenant_id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        phone=lead.phone,
        source=lead.source,
        status=lead.status,
        assigned_to=lead.assigned_to,
        notes=lead.notes,
        lost_reason=lead.lost_reason,
        converted_member_id=lead.converted_member_id,
        custom_fields=lead.custom_fields,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def _to_activity_response(a: LeadActivity) -> LeadActivityResponse:
    return LeadActivityResponse(
        id=a.id,
        tenant_id=a.tenant_id,
        lead_id=a.lead_id,
        type=a.type,
        note=a.note,
        created_by=a.created_by,
        created_at=a.created_at,
    )


def _to_member_summary(m: Member) -> ConvertedMemberSummary:
    return ConvertedMemberSummary(
        id=m.id,
        tenant_id=m.tenant_id,
        first_name=m.first_name,
        last_name=m.last_name,
        phone=m.phone,
        email=m.email,
        status=m.status,
        join_date=m.join_date,
        notes=m.notes,
    )


def _to_sub_summary(s: Subscription) -> ConvertedSubscriptionSummary:
    return ConvertedSubscriptionSummary(
        id=s.id,
        tenant_id=s.tenant_id,
        member_id=s.member_id,
        plan_id=s.plan_id,
        status=s.status,
        started_at=s.started_at,
        expires_at=s.expires_at,
        price_cents=s.price_cents,
        currency=s.currency,
    )


def _to_convert_response(result: ConvertResult) -> ConvertLeadResponse:
    return ConvertLeadResponse(
        lead=_to_lead_response(result.lead),
        member=_to_member_summary(result.member),
        subscription=_to_sub_summary(result.subscription),
    )


# ── Lead CRUD ─────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead (sales+)",
)
async def create_lead(
    body: CreateLeadRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadResponse:
    lead = await service.create(
        caller=caller,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        email=body.email,
        source=body.source,
        assigned_to=body.assigned_to,
        notes=body.notes,
        custom_fields=body.custom_fields,
    )
    return _to_lead_response(lead)


@router.get(
    "",
    response_model=list[LeadResponse],
    summary="List leads in the caller's tenant",
)
async def list_leads(
    status_filter: list[LeadStatus] | None = Query(default=None, alias="status"),
    source_filter: list[LeadSource] | None = Query(default=None, alias="source"),
    assigned_to: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> list[LeadResponse]:
    leads = await service.list_for_tenant(
        caller=caller,
        status=status_filter,
        source=source_filter,
        assigned_to=assigned_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [_to_lead_response(lead) for lead in leads]


@router.get(
    "/stats",
    response_model=LeadStatsResponse,
    summary="Pipeline counts + 30-day conversion rate",
)
async def get_stats(
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadStatsResponse:
    stats = await service.stats(caller=caller)
    return LeadStatsResponse(
        counts=stats.counts,
        conversion_rate_30d=stats.conversion_rate_30d,
    )


@router.get(
    "/lost-reasons",
    response_model=list[LostReasonRowResponse],
    summary="Top lost reasons in the last N days (for autocomplete)",
)
async def list_lost_reasons(
    days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> list[LostReasonRowResponse]:
    rows = await service.list_lost_reasons(caller=caller, days=days, limit=limit)
    return [LostReasonRowResponse(reason=r.reason, count=r.count) for r in rows]


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Fetch a single lead",
)
async def get_lead(
    lead_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadResponse:
    return _to_lead_response(await service.get(caller=caller, lead_id=lead_id))


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Update lead fields (sales+)",
)
async def update_lead(
    lead_id: UUID,
    body: UpdateLeadRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadResponse:
    fields = body.model_dump(exclude_unset=True)
    updated = await service.update(caller=caller, lead_id=lead_id, **fields)
    return _to_lead_response(updated)


@router.post(
    "/{lead_id}/status",
    response_model=LeadResponse,
    summary="Move a lead through the pipeline (sales+)",
)
async def set_status(
    lead_id: UUID,
    body: SetStatusRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadResponse:
    updated = await service.set_status(
        caller=caller,
        lead_id=lead_id,
        new_status=body.new_status,
        lost_reason=body.lost_reason,
    )
    return _to_lead_response(updated)


@router.post(
    "/{lead_id}/assign",
    response_model=LeadResponse,
    summary="Assign or unassign a lead (sales+)",
)
async def assign_lead(
    lead_id: UUID,
    body: AssignLeadRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadResponse:
    updated = await service.assign(caller=caller, lead_id=lead_id, user_id=body.user_id)
    return _to_lead_response(updated)


@router.post(
    "/{lead_id}/convert",
    response_model=ConvertLeadResponse,
    summary="Convert a lead to a Member + Subscription (sales+)",
)
async def convert_lead(
    lead_id: UUID,
    body: ConvertLeadRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> ConvertLeadResponse:
    result = await service.convert(
        caller=caller,
        lead_id=lead_id,
        plan_id=body.plan_id,
        payment_method=body.payment_method,
        start_date=body.start_date,
        copy_notes_to_member=body.copy_notes_to_member,
    )
    return _to_convert_response(result)


# ── Activities ────────────────────────────────────────────────────────


@router.get(
    "/{lead_id}/activities",
    response_model=list[LeadActivityResponse],
    summary="Lead's activity timeline (newest first)",
)
async def list_activities(
    lead_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> list[LeadActivityResponse]:
    rows = await service.list_activities(caller=caller, lead_id=lead_id, limit=limit, offset=offset)
    return [_to_activity_response(r) for r in rows]


@router.post(
    "/{lead_id}/activities",
    response_model=LeadActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log an activity (sales+). status_change is system-only.",
)
async def add_activity(
    lead_id: UUID,
    body: AddActivityRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: LeadService = Depends(_get_service),
) -> LeadActivityResponse:
    activity = await service.add_activity(
        caller=caller,
        lead_id=lead_id,
        type=body.type,
        note=body.note,
    )
    return _to_activity_response(activity)
