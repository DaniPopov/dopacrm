"""Member CRUD routes — ``/api/v1/members``.

Thin layer. Validates HTTP input, calls MemberService, returns HTTP output.
All business logic (tenant scoping, status transitions, permission
checks) lives in the service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.members.schemas import (
    CreateMemberRequest,
    FreezeMemberRequest,
    MemberResponse,
    UpdateMemberRequest,
)
from app.api.v1.payments.schemas import PaymentResponse
from app.core.security import TokenPayload
from app.domain.entities.member import Member, MemberStatus
from app.domain.entities.payment import Payment
from app.services.member_service import MemberService
from app.services.payment_service import PaymentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> MemberService:
    """FastAPI dependency that creates a MemberService per request."""
    return MemberService(session)


def _to_response(member: Member) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        first_name=member.first_name,
        last_name=member.last_name,
        phone=member.phone,
        email=member.email,
        date_of_birth=member.date_of_birth,
        gender=member.gender,
        status=member.status,
        join_date=member.join_date,
        frozen_at=member.frozen_at,
        frozen_until=member.frozen_until,
        cancelled_at=member.cancelled_at,
        notes=member.notes,
        custom_fields=member.custom_fields,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.post(
    "",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new member",
    description="Creates a member in the caller's tenant. Phone must be unique within the tenant.",
)
async def create_member(
    body: CreateMemberRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.create(
        caller=caller,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        email=body.email,
        date_of_birth=body.date_of_birth,
        gender=body.gender,
        join_date=body.join_date,
        notes=body.notes,
        custom_fields=body.custom_fields,
    )
    return _to_response(member)


@router.get(
    "",
    response_model=list[MemberResponse],
    summary="List members",
    description="List members in the caller's tenant. Filterable by status and search.",
)
async def list_members(
    status_filter: list[MemberStatus] | None = Query(
        default=None, alias="status", description="Repeat to filter multiple"
    ),
    search: str | None = Query(
        default=None, description="Case-insensitive match against name, phone, email"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> list[MemberResponse]:
    members = await service.list_for_tenant(
        caller=caller, status=status_filter, search=search, limit=limit, offset=offset
    )
    return [_to_response(m) for m in members]


@router.get(
    "/{member_id}",
    response_model=MemberResponse,
    summary="Get a member by ID",
)
async def get_member(
    member_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.get(caller=caller, member_id=member_id)
    return _to_response(member)


@router.patch(
    "/{member_id}",
    response_model=MemberResponse,
    summary="Update a member (partial)",
)
async def update_member(
    member_id: UUID,
    body: UpdateMemberRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    updates = body.model_dump(exclude_unset=True)
    member = await service.update(caller=caller, member_id=member_id, **updates)
    return _to_response(member)


@router.post(
    "/{member_id}/freeze",
    response_model=MemberResponse,
    summary="Freeze a member",
    description="Pauses the subscription without cancelling. Only active members can be frozen.",
)
async def freeze_member(
    member_id: UUID,
    body: FreezeMemberRequest | None = None,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    until = body.until if body else None
    member = await service.freeze(caller=caller, member_id=member_id, until=until)
    return _to_response(member)


@router.post(
    "/{member_id}/unfreeze",
    response_model=MemberResponse,
    summary="Unfreeze a member",
    description="Returns a frozen member to active status.",
)
async def unfreeze_member(
    member_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.unfreeze(caller=caller, member_id=member_id)
    return _to_response(member)


@router.post(
    "/{member_id}/cancel",
    response_model=MemberResponse,
    summary="Cancel a member (terminal)",
    description="owner+ only. Sets status=cancelled. Data is preserved.",
)
async def cancel_member(
    member_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.cancel(caller=caller, member_id=member_id)
    return _to_response(member)


def _get_payment_service(session: AsyncSession = Depends(get_session)) -> PaymentService:
    return PaymentService(session)


def _to_payment_response(p: Payment) -> PaymentResponse:
    return PaymentResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        member_id=p.member_id,
        subscription_id=p.subscription_id,
        amount_cents=p.amount_cents,
        currency=p.currency,
        payment_method=p.payment_method,
        paid_at=p.paid_at,
        notes=p.notes,
        refund_of_payment_id=p.refund_of_payment_id,
        external_ref=p.external_ref,
        recorded_by=p.recorded_by,
        created_at=p.created_at,
    )


@router.get(
    "/{member_id}/payments",
    response_model=list[PaymentResponse],
    summary="List payments for one member (newest first)",
    description=(
        "Convenience endpoint — same as ``GET /payments?member_id={id}`` but "
        "lives next to the member detail page that consumes it."
    ),
)
async def list_member_payments(
    member_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_payment_service),
) -> list[PaymentResponse]:
    payments = await service.list_for_member(caller=caller, member_id=member_id)
    return [_to_payment_response(p) for p in payments]
