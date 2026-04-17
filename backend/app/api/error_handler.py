"""Global exception handler — maps domain AppError to HTTP responses.

Registered once in ``main.py`` via ``app.add_exception_handler``.
Services and adapters raise ``AppError`` subclasses; this handler
translates the error ``code`` to an HTTP status code and returns a
consistent JSON response body.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from app.domain.exceptions import AppError

if TYPE_CHECKING:
    from starlette.requests import Request

#: Map AppError.code → HTTP status code. Add new entries as exceptions grow.
_STATUS_MAP: dict[str, int] = {
    # Auth
    "INVALID_CREDENTIALS": 401,
    "INSUFFICIENT_PERMISSIONS": 403,
    # User
    "USER_NOT_FOUND": 404,
    "USER_ALREADY_EXISTS": 409,
    # Tenant
    "TENANT_NOT_FOUND": 404,
    "TENANT_SUSPENDED": 403,
    "TENANT_SLUG_TAKEN": 409,
    # Member
    "MEMBER_NOT_FOUND": 404,
    "MEMBER_ALREADY_EXISTS": 409,
    "MEMBER_INVALID_TRANSITION": 409,
    # Class
    "CLASS_NOT_FOUND": 404,
    "CLASS_ALREADY_EXISTS": 409,
    # Membership Plan
    "PLAN_NOT_FOUND": 404,
    "PLAN_ALREADY_EXISTS": 409,
    "PLAN_INVALID_SHAPE": 422,
    # Subscription
    "SUBSCRIPTION_NOT_FOUND": 404,
    "SUBSCRIPTION_INVALID_TRANSITION": 409,
    "MEMBER_HAS_ACTIVE_SUBSCRIPTION": 409,
    "SUBSCRIPTION_SAME_PLAN": 409,
    "SUBSCRIPTION_PLAN_TENANT_MISMATCH": 422,
}

#: Fallback for unmapped codes.
_DEFAULT_STATUS = 500


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Convert an AppError into a JSON response with the appropriate status."""
    status_code = _STATUS_MAP.get(exc.code, _DEFAULT_STATUS)
    return JSONResponse(
        status_code=status_code,
        content={"error": exc.code, "detail": exc.message},
    )
