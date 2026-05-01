"""Dashboard routes — ``/api/v1/dashboard``.

Aggregation endpoints that back the GymDashboard widgets. Each
endpoint is a single read-only summary; no business state changes
here.

v1 ships ``/revenue`` (consumed by the Payments + revenue widgets).
Future widgets (member churn, attendance trends, lead conversion
funnel) bolt on as additional endpoints in this router.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.payments.schemas import (
    PlanRevenueRowResponse,
    RangeRevenueResponse,
    RevenueSummaryResponse,
)
from app.core.security import TokenPayload
from app.services.payment_service import PaymentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_payment_service(session: AsyncSession = Depends(get_session)) -> PaymentService:
    return PaymentService(session)


@router.get(
    "/revenue",
    response_model=RevenueSummaryResponse,
    summary="Revenue summary — this month, last month, MoM, by-plan, by-method, ARPM",
)
async def revenue_summary(
    caller: TokenPayload = Depends(get_current_user),
    service: PaymentService = Depends(_get_payment_service),
) -> RevenueSummaryResponse:
    summary = await service.revenue_summary(caller=caller)
    return RevenueSummaryResponse(
        currency=summary.currency,
        this_month=RangeRevenueResponse(
            paid_from=summary.this_month.paid_from,
            paid_to=summary.this_month.paid_to,
            cents=summary.this_month.cents,
        ),
        last_month=RangeRevenueResponse(
            paid_from=summary.last_month.paid_from,
            paid_to=summary.last_month.paid_to,
            cents=summary.last_month.cents,
        ),
        mom_pct=summary.mom_pct,
        by_plan=[
            PlanRevenueRowResponse(plan_id=row.plan_id, cents=row.cents) for row in summary.by_plan
        ],
        by_method=summary.by_method,
        arpm_cents=summary.arpm_cents,
    )
