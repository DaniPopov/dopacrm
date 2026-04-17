"""User CRUD routes — ``/api/v1/users``.

Thin layer — validates HTTP input, calls UserService, returns HTTP output.
All business logic (permission checks, company scoping) lives in the service.

Routes NEVER import repositories directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import (
    get_current_user,
    require_owner,
    require_super_admin,
)
from app.api.dependencies.database import get_session
from app.api.v1.users.schemas import CreateUserRequest, UpdateUserRequest, UserResponse
from app.core.security import TokenPayload
from app.services.user_service import UserService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> UserService:
    """FastAPI dependency that creates a UserService per request."""
    return UserService(session)


def _to_response(user) -> UserResponse:
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


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Only super_admin can create users. Tenant-scoped roles "
    "(admin/manager/worker) require a tenant_id.",
)
async def create_user(
    body: CreateUserRequest,
    caller: TokenPayload = Depends(require_super_admin),
    service: UserService = Depends(_get_service),
) -> UserResponse:
    user = await service.create_user(
        caller=caller,
        email=body.email,
        role=body.role,
        tenant_id=body.tenant_id,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        oauth_provider=body.oauth_provider,
        oauth_id=body.oauth_id,
    )
    return _to_response(user)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List users",
    description="super_admin sees all users. owner/staff/sales see only their tenant.",
)
async def list_users(
    limit: int = Query(default=50, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip N results"),
    caller: TokenPayload = Depends(get_current_user),
    service: UserService = Depends(_get_service),
) -> list[UserResponse]:
    users = await service.list_users(caller, limit=limit, offset=offset)
    return [_to_response(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID",
)
async def get_user(
    user_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: UserService = Depends(_get_service),
) -> UserResponse:
    user = await service.get_user(caller=caller, user_id=user_id)
    return _to_response(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user (partial)",
    description="Owner or above. Only provided fields are updated.",
)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    caller: TokenPayload = Depends(require_owner),
    service: UserService = Depends(_get_service),
) -> UserResponse:
    updates = body.model_dump(exclude_unset=True)
    user = await service.update_user(caller=caller, user_id=user_id, **updates)
    return _to_response(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a user",
    description="Sets is_active=false. No data is removed. Owner or above.",
)
async def delete_user(
    user_id: UUID,
    caller: TokenPayload = Depends(require_owner),
    service: UserService = Depends(_get_service),
) -> None:
    await service.soft_delete_user(caller=caller, user_id=user_id)
