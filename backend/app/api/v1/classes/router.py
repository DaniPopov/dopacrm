"""Gym class CRUD routes — ``/api/v1/classes``.

Thin layer. Validates HTTP input, calls GymClassService, returns HTTP
output. All business logic (tenant scoping, permission checks, status
transitions) lives in the service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.v1.classes.schemas import (
    CreateGymClassRequest,
    GymClassResponse,
    UpdateGymClassRequest,
)
from app.core.security import TokenPayload
from app.domain.entities.gym_class import GymClass
from app.services.gym_class_service import GymClassService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> GymClassService:
    return GymClassService(session)


def _to_response(cls: GymClass) -> GymClassResponse:
    return GymClassResponse(
        id=cls.id,
        tenant_id=cls.tenant_id,
        name=cls.name,
        description=cls.description,
        color=cls.color,
        is_active=cls.is_active,
        created_at=cls.created_at,
        updated_at=cls.updated_at,
    )


@router.post(
    "",
    response_model=GymClassResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class type",
    description=(
        "Owner-only. Creates a new class type in the caller's tenant. "
        "Name must be unique within the tenant."
    ),
)
async def create_class(
    body: CreateGymClassRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> GymClassResponse:
    cls = await service.create(
        caller=caller,
        name=body.name,
        description=body.description,
        color=body.color,
    )
    return _to_response(cls)


@router.get(
    "",
    response_model=list[GymClassResponse],
    summary="List class types",
    description=(
        "Lists classes in the caller's tenant. Any tenant user can read. "
        "Pass ``include_inactive=true`` (owner) to see deactivated classes."
    ),
)
async def list_classes(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> list[GymClassResponse]:
    classes = await service.list_for_tenant(
        caller=caller,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return [_to_response(c) for c in classes]


@router.get(
    "/{class_id}",
    response_model=GymClassResponse,
    summary="Get a class by ID",
)
async def get_class(
    class_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> GymClassResponse:
    cls = await service.get(caller=caller, class_id=class_id)
    return _to_response(cls)


@router.patch(
    "/{class_id}",
    response_model=GymClassResponse,
    summary="Update a class (partial)",
    description="Owner-only. Rename, re-color, edit description.",
)
async def update_class(
    class_id: UUID,
    body: UpdateGymClassRequest,
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> GymClassResponse:
    updates = body.model_dump(exclude_unset=True)
    cls = await service.update(caller=caller, class_id=class_id, **updates)
    return _to_response(cls)


@router.post(
    "/{class_id}/deactivate",
    response_model=GymClassResponse,
    summary="Deactivate a class (soft)",
    description=(
        "Owner-only. Sets is_active=false — existing plan_entitlements and "
        "class_passes keep working, but new subscriptions can't reference this class."
    ),
)
async def deactivate_class(
    class_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> GymClassResponse:
    cls = await service.deactivate(caller=caller, class_id=class_id)
    return _to_response(cls)


@router.post(
    "/{class_id}/activate",
    response_model=GymClassResponse,
    summary="Re-activate a deactivated class",
    description="Owner-only. Sets is_active=true.",
)
async def activate_class(
    class_id: UUID,
    caller: TokenPayload = Depends(get_current_user),
    service: GymClassService = Depends(_get_service),
) -> GymClassResponse:
    cls = await service.activate(caller=caller, class_id=class_id)
    return _to_response(cls)
