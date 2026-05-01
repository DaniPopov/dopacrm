"""Payments routes — ``/api/v1/payments``.

Thin Layer 1. All business logic (tenant scoping, role gates, refund
math, currency snapshot, append-only enforcement) lives in
``PaymentService``.

No ``PATCH`` and no ``DELETE`` endpoints — append-only is enforced at
the API surface, not just the service. Mistakes are corrected via
the dedicated ``/refund`` endpoint.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.payments.schemas import (
    PaymentResponse,
    RecordPaymentRequest,
    RefundPaymentRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.payment import Payment
from app.domain.entities.subscription import PaymentMethod
from app.services.payment_service import PaymentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> PaymentService:
    return PaymentService(session)


def _to_response(p: Payment) -> PaymentResponse:
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


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment (staff+)",
)
async def record_payment(
    body: RecordPaymentRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_service),
) -> PaymentResponse:
    payment = await service.record(
        caller=caller,
        member_id=body.member_id,
        amount_cents=body.amount_cents,
        payment_method=body.payment_method,
        paid_at=body.paid_at,
        subscription_id=body.subscription_id,
        notes=body.notes,
        external_ref=body.external_ref,
        backdate=body.backdate,
    )
    return _to_response(payment)


@router.get(
    "",
    response_model=list[PaymentResponse],
    summary="List payments in the caller's tenant",
)
async def list_payments(
    member_id: UUID | None = Query(default=None),
    subscription_id: UUID | None = Query(default=None),
    paid_from: date | None = Query(default=None),
    paid_to: date | None = Query(default=None),
    method: PaymentMethod | None = Query(default=None),
    include_refunds: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_service),
) -> list[PaymentResponse]:
    payments = await service.list_for_tenant(
        caller=caller,
        member_id=member_id,
        subscription_id=subscription_id,
        paid_from=paid_from,
        paid_to=paid_to,
        method=method,
        include_refunds=include_refunds,
        limit=limit,
        offset=offset,
    )
    return [_to_response(p) for p in payments]


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Fetch a single payment",
)
async def get_payment(
    payment_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_service),
) -> PaymentResponse:
    return _to_response(await service.get(caller=caller, payment_id=payment_id))


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentResponse,
    summary="Refund a payment (owner+) — appends a negative-amount row",
)
async def refund_payment(
    payment_id: UUID,
    body: RefundPaymentRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_service),
) -> PaymentResponse:
    refund = await service.refund(
        caller=caller,
        payment_id=payment_id,
        amount_cents=body.amount_cents,
        reason=body.reason,
    )
    return _to_response(refund)
