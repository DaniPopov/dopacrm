"""Tenant CRUD routes — ``/api/v1/tenants``.

Thin layer — validates HTTP input, calls TenantService, returns HTTP output.
All business logic (permission checks, slug validation) lives in the service.

Routes NEVER import repositories directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user, require_super_admin
from app.api.dependencies.database import get_session
from app.api.v1.tenants.schemas import (
    CreateTenantRequest,
    TenantResponse,
    UpdateTenantRequest,
)
from app.core.security import TokenPayload
from app.services.tenant_service import TenantService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> TenantService:
    """FastAPI dependency that creates a TenantService per request."""
    return TenantService(session)


def _to_response(tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        phone=tenant.phone,
        status=tenant.status,
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
    _caller: TokenPayload = Depends(get_current_user),
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.get_tenant(tenant_id)
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
