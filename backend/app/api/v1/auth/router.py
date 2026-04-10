"""Auth routes — ``/api/v1/auth``.

- ``POST /login`` — email + password → JWT in HttpOnly cookie + response body
- ``POST /logout`` — clears the HttpOnly cookie
- ``GET /me`` — current user profile from token
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.adapters.storage.postgres.user.repositories import UserRepository
from app.api.dependencies.auth import COOKIE_NAME, get_current_user
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


def _set_token_cookie(response: Response, token: str, *, is_production: bool) -> None:
    """Set the JWT as an HttpOnly cookie."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=int(ACCESS_TOKEN_EXPIRE.total_seconds()),
        path="/",
    )


def _clear_token_cookie(response: Response, *, is_production: bool) -> None:
    """Clear the JWT cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    description="Returns a JWT access token in an HttpOnly cookie (for the frontend) "
    "and in the response body (for Swagger / API clients). "
    "Rate limited: 10 requests per minute per IP.",
    dependencies=login_rate_limit,
)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()
    repo = UserRepository(session)

    # Look up user by email. Try super_admin first (tenant_id IS NULL),
    # then search across all tenants.
    result = await repo.find_with_credentials(body.email, tenant_id=None)
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

    # Set HttpOnly cookie for the frontend
    _set_token_cookie(response, token, is_production=settings.is_production)

    # Also return in body for Swagger / API clients
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(ACCESS_TOKEN_EXPIRE.total_seconds()),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout",
    description="Clears the HttpOnly cookie and blacklists the token in Redis "
    "so it can't be reused even if intercepted.",
)
async def logout(
    response: Response,
    caller: TokenPayload = Depends(get_current_user),
) -> None:
    from app.core.token_blacklist import blacklist_token

    settings = get_settings()

    # Blacklist the token in Redis until it expires
    if caller.jti and caller.exp:
        await blacklist_token(caller.jti, caller.exp)

    _clear_token_cookie(response, is_production=settings.is_production)


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
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
