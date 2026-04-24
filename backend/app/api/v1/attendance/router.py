"""Attendance / check-in routes — ``/api/v1/attendance``.

Thin Layer 1. Validates HTTP input, calls AttendanceService, formats
output. All business logic (tenant scoping, role gates, quota math,
structlog) lives in the service.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.attendance.schemas import (
    EntryResponse,
    QuotaCheckResponse,
    ReassignCoachRequest,
    RecordEntryRequest,
    SummaryItem,
    UndoEntryRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.class_entry import ClassEntry
from app.services.attendance_service import AttendanceService, QuotaCheckResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> AttendanceService:
    return AttendanceService(session)


def _to_response(entry: ClassEntry) -> EntryResponse:
    return EntryResponse(
        id=entry.id,
        tenant_id=entry.tenant_id,
        member_id=entry.member_id,
        subscription_id=entry.subscription_id,
        class_id=entry.class_id,
        entered_at=entry.entered_at,
        entered_by=entry.entered_by,
        undone_at=entry.undone_at,
        undone_by=entry.undone_by,
        undone_reason=entry.undone_reason,
        override=entry.override,
        override_kind=entry.override_kind,
        override_reason=entry.override_reason,
        coach_id=entry.coach_id,
    )


def _quota_to_response(q: QuotaCheckResult) -> QuotaCheckResponse:
    return QuotaCheckResponse(
        allowed=q.allowed,
        remaining=q.remaining,
        used=q.used,
        quantity=q.quantity,
        reset_period=q.reset_period,
        reason=q.reason,
        class_id=q.class_id,
    )


# ── Commands ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a check-in",
    description=(
        "staff+. Quota is checked first. If the member is at quota or the "
        "class isn't covered, the server returns 409 and the UI shows an "
        "override modal; retry with ``override=true`` to record anyway "
        "(flagged for owner audit)."
    ),
)
async def record_entry(
    body: RecordEntryRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> EntryResponse:
    entry = await service.record_entry(
        caller=caller,
        member_id=body.member_id,
        class_id=body.class_id,
        override=body.override,
        override_reason=body.override_reason,
    )
    return _to_response(entry)


@router.post(
    "/{entry_id}/undo",
    response_model=EntryResponse,
    summary="Undo a check-in (within 24h)",
    description=(
        "staff+. Soft-deletes the entry. Returns 409 if past the 24h "
        "window or already undone. The row stays in the DB so reporting "
        "remains honest."
    ),
)
async def undo_entry(
    entry_id: UUID,
    body: UndoEntryRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> EntryResponse:
    entry = await service.undo(caller=caller, entry_id=entry_id, reason=body.reason)
    return _to_response(entry)


# ── Queries ─────────────────────────────────────────────────────────────


@router.get(
    "/quota-check",
    response_model=QuotaCheckResponse,
    summary="Peek at whether a check-in would be allowed",
    description=(
        "Returns the quota status for one (member, class) pair WITHOUT "
        "recording anything. Used by the check-in page to color class "
        "cards (covered / not-covered / at-quota with a remaining count)."
    ),
)
async def quota_check(
    member_id: UUID,
    class_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> QuotaCheckResponse:
    result = await service.quota_check(caller=caller, member_id=member_id, class_id=class_id)
    return _quota_to_response(result)


@router.get(
    "",
    response_model=list[EntryResponse],
    summary="List entries in the caller's tenant",
    description=(
        "Filterable: ``member_id``, ``class_id``, ``date_from``, "
        "``date_to``, ``include_undone``, ``undone_only``, ``override_only``. "
        "The last two power the owner's 'mistakes / overrides this week' views."
    ),
)
async def list_entries(
    member_id: UUID | None = Query(default=None),
    class_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    include_undone: bool = Query(default=False),
    undone_only: bool = Query(default=False),
    override_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> list[EntryResponse]:
    entries = await service.list_for_tenant(
        caller=caller,
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
    return [_to_response(e) for e in entries]


@router.get(
    "/members/{member_id}",
    response_model=list[EntryResponse],
    summary="Full attendance history for one member",
    description="Shown on the member detail page. Includes undone entries.",
)
async def list_member_entries(
    member_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> list[EntryResponse]:
    entries = await service.list_for_member(caller=caller, member_id=member_id, limit=limit)
    return [_to_response(e) for e in entries]


@router.get(
    "/members/{member_id}/summary",
    response_model=list[SummaryItem],
    summary="Per-entitlement usage summary for a member",
    description=(
        "One row per entitlement on the member's live sub. UNLIMITED "
        "shows up with ``remaining=null``. Empty list if no live sub. "
        "Used by the check-in page header + the member self-view (future)."
    ),
)
async def member_summary(
    member_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> list[SummaryItem]:
    results = await service.summary_for_member(caller=caller, member_id=member_id)
    return [
        SummaryItem(
            allowed=r.allowed,
            remaining=r.remaining,
            used=r.used,
            quantity=r.quantity,
            reset_period=r.reset_period,
            reason=r.reason,
            class_id=r.class_id,
        )
        for r in results
    ]


@router.post(
    "/{entry_id}/reassign-coach",
    response_model=EntryResponse,
    summary="Reassign the coach_id on an entry (owner+)",
    description=(
        "Admin correction of a mis-attributed entry. Pass ``coach_id=null`` "
        "to clear the attribution. Emits ``attendance.coach_reassigned`` to "
        "the structlog audit trail."
    ),
)
async def reassign_coach(
    entry_id: UUID,
    body: ReassignCoachRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: AttendanceService = Depends(_get_service),
) -> EntryResponse:
    entry = await service.reassign_coach(caller=caller, entry_id=entry_id, coach_id=body.coach_id)
    return _to_response(entry)
