"""Auth routes — ``/api/v1/auth``.

- ``POST /login`` — JSON email + password → access token
- ``GET /me`` — return current user info from token
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.adapters.storage.postgres.user.repositories import UserRepository
from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_session
from app.api.dependencies.rate_limit import login_rate_limit
from app.api.v1.auth.schemas import LoginRequest, TokenResponse
from app.api.v1.users.schemas import UserResponse
from app.core.config import get_settings
from app.core.security import (
    ACCESS_TOKEN_EXPIRE,
    TokenPayload,
    create_access_token,
    verify_password,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    description="Returns a JWT access token. Copy it and paste in the "
    "**Authorize** button (lock icon, top-right) to authenticate. "
    "Rate limited: 10 requests per minute per IP.",
    dependencies=login_rate_limit,
)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()
    repo = UserRepository(session)

    # Look up user by email. For company-scoped users, the frontend
    # will eventually pass tenant_id (or we resolve it from a subdomain).
    # For now: try super_admin first, then search by email WITH tenant_id
    # attached to the user row — never query without tenant scoping.
    result = await repo.find_with_credentials(body.email, tenant_id=None)

    # If not super_admin, try company-scoped lookup.
    # find_with_credentials with tenant_id=None uses WHERE tenant_id IS NULL.
    # For company users, we need to find which company they belong to.
    # Safe approach: look up by email across all companies via the repo
    # (still parameterized SQL, still returns one user).
    if result is None:
        result = await repo.find_any_by_email_with_credentials(body.email)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user, password_hash = result

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    if password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses OAuth — password login is not available",
        )

    if not verify_password(body.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        tenant_id=user.tenant_id,
        secret_key=settings.APP_SECRET_KEY.get_secret_value(),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(ACCESS_TOKEN_EXPIRE.total_seconds()),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the user profile for the authenticated token.",
)
async def me(
    caller: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    repo = UserRepository(session)
    user = await repo.find_by_id(UUID(caller.sub))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        is_active=user.is_active,
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
