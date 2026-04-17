"""Tenant CRUD routes — ``/api/v1/tenants``.

Thin layer — validates HTTP input, calls TenantService, returns HTTP output.
All business logic (permission checks, slug validation) lives in the service.

Routes NEVER import repositories directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.adapters.storage.s3 import generate_presigned_url
from app.api.dependencies.auth import get_current_user, require_super_admin
from app.api.dependencies.database import get_session
from app.api.v1.tenants.schemas import (
    CreateTenantRequest,
    TenantResponse,
    TenantStatsResponse,
    UpdateTenantRequest,
)
from app.api.v1.users.schemas import UserResponse
from app.core.logger import get_logger
from app.core.security import TokenPayload
from app.services.tenant_service import TenantService

logger = get_logger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> TenantService:
    """FastAPI dependency that creates a TenantService per request."""
    return TenantService(session)


def _presign_logo(logo_url: str | None) -> str | None:
    """Generate a 1-hour presigned URL for a logo S3 key, or None."""
    if not logo_url:
        return None
    try:
        return generate_presigned_url(logo_url, expires_in=3600)
    except Exception:
        logger.warning("presign_failed", key=logo_url)
        return None


def _to_response(tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        saas_plan_id=tenant.saas_plan_id,
        logo_url=tenant.logo_url,
        logo_presigned_url=_presign_logo(tenant.logo_url),
        phone=tenant.phone,
        email=tenant.email,
        website=tenant.website,
        address_street=tenant.address_street,
        address_city=tenant.address_city,
        address_country=tenant.address_country,
        address_postal_code=tenant.address_postal_code,
        legal_name=tenant.legal_name,
        tax_id=tenant.tax_id,
        timezone=tenant.timezone,
        currency=tenant.currency,
        locale=tenant.locale,
        trial_ends_at=tenant.trial_ends_at,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard a new gym",
    description="Only super_admin can create tenants.",
)
async def create_tenant(
    body: CreateTenantRequest,
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.create_tenant(
        caller=caller,
        slug=body.slug,
        name=body.name,
        phone=body.phone,
        logo_url=body.logo_url,
        email=body.email,
        website=body.website,
        address_street=body.address_street,
        address_city=body.address_city,
        address_country=body.address_country,
        address_postal_code=body.address_postal_code,
        legal_name=body.legal_name,
        tax_id=body.tax_id,
        timezone=body.timezone,
        currency=body.currency,
        locale=body.locale,
    )
    return _to_response(tenant)


@router.get(
    "",
    response_model=list[TenantResponse],
    summary="List all tenants",
    description="super_admin only. Returns all gyms on the platform.",
)
async def list_tenants(
    limit: int = Query(default=50, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip N results"),
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> list[TenantResponse]:
    tenants = await service.list_tenants(caller=caller, limit=limit, offset=offset)
    return [_to_response(t) for t in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get a tenant by ID",
)
async def get_tenant(
    tenant_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.get_tenant(caller=caller, tenant_id=tenant_id)
    return _to_response(tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update a tenant (partial)",
    description="super_admin only. Only provided fields are updated.",
)
async def update_tenant(
    tenant_id: UUID,
    body: UpdateTenantRequest,
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    updates = body.model_dump(exclude_unset=True)
    tenant = await service.update_tenant(caller=caller, tenant_id=tenant_id, **updates)
    return _to_response(tenant)


@router.post(
    "/{tenant_id}/suspend",
    response_model=TenantResponse,
    summary="Suspend a tenant",
    description="super_admin only. Blocks all users of this gym from accessing the platform.",
)
async def suspend_tenant(
    tenant_id: UUID,
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.suspend_tenant(caller=caller, tenant_id=tenant_id)
    return _to_response(tenant)


@router.post(
    "/{tenant_id}/activate",
    response_model=TenantResponse,
    summary="Activate a tenant",
    description="super_admin only. Moves a tenant to active (from trial, suspended, or cancelled).",
)
async def activate_tenant(
    tenant_id: UUID,
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.activate_tenant(caller=caller, tenant_id=tenant_id)
    return _to_response(tenant)


@router.post(
    "/{tenant_id}/cancel",
    response_model=TenantResponse,
    summary="Cancel a tenant (soft delete)",
    description=(
        "super_admin only. Sets status to cancelled. Data is preserved; "
        "this is reversible by calling /activate."
    ),
)
async def cancel_tenant(
    tenant_id: UUID,
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.cancel_tenant(caller=caller, tenant_id=tenant_id)
    return _to_response(tenant)


# ── Nested: tenant-scoped stats + users ──────────────────────────────────────


@router.get(
    "/{tenant_id}/stats",
    response_model=TenantStatsResponse,
    summary="Per-tenant stats",
    description=(
        "Counts for the tenant detail page — members (total + active) and users. "
        "super_admin can view any tenant; tenant users can only view their own."
    ),
)
async def get_tenant_stats(
    tenant_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: TenantService = Depends(_get_service),
) -> TenantStatsResponse:
    stats = await service.get_stats(caller=caller, tenant_id=tenant_id)
    return TenantStatsResponse(**stats)


def _user_to_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        is_active=user.is_active,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get(
    "/{tenant_id}/users",
    response_model=list[UserResponse],
    summary="List users of a tenant",
    description="super_admin only. Use GET /users instead for self-tenant listing.",
)
async def list_tenant_users(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(require_super_admin),
    service: TenantService = Depends(_get_service),
) -> list[UserResponse]:
    users = await service.list_users_for_tenant(
        caller=caller, tenant_id=tenant_id, limit=limit, offset=offset
    )
    return [_user_to_response(u) for u in users]
