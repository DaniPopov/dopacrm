"""Platform admin routes — ``/api/v1/admin/...``.

Everything here is super_admin only. Today it's just the aggregate
stats endpoint for the AdminDashboard, but this is where future
cross-tenant operations (platform settings, plan management,
analytics) will live.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_super_admin
from app.api.dependencies.database import get_session
from app.api.v1.admin.schemas import PlatformStatsResponse
from app.core.security import TokenPayload
from app.services.tenant_service import TenantService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> TenantService:
    return TenantService(session)


@router.get(
    "/stats",
    response_model=PlatformStatsResponse,
    summary="Platform-wide aggregate counts",
    description=(
        "super_admin only. Returns total/active tenant counts, "
        "new-tenants-this-month, total users, and total members across "
        "all tenants. Powers the admin dashboard."
    ),
)
async def get_platform_stats(
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> PlatformStatsResponse:
    stats = await service.get_platform_stats(caller=caller)
    return PlatformStatsResponse(**stats)
