"""Structured access logging middleware.

Logs every request with consistent, prefix-grouped fields:

    request_id            unique correlation ID (uuid4 if absent)
    http_method           GET / POST / PATCH / ...
    http_path             url path
    http_query            url query string (None if absent)
    http_status           response status code
    http_duration_ms      total request duration, milliseconds
    http_response_bytes   response Content-Length if known
    client_ip             X-Forwarded-For / X-Real-IP / socket peer
    user_agent            User-Agent header

The request_id is also bound to structlog contextvars so any log line
emitted by handlers during the request inherits it (correlation across
multiple log lines from the same request).

Sensitive headers (Authorization, Cookie, X-API-Key) are never logged.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import get_logger

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

logger = get_logger("app.access")


def _client_ip(request: Request) -> str:
    """Best-effort client IP — honors X-Forwarded-For / X-Real-IP from proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can be a chain: "client, proxy1, proxy2"
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request as a structured event."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        client_ip = _client_ip(request)
        http_method = request.method
        http_path = request.url.path
        http_query = str(request.url.query) or None
        user_agent = request.headers.get("user-agent")

        # Bind request-scoped context — every log line emitted during this
        # request inherits these fields automatically.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=http_method,
            http_path=http_path,
            client_ip=client_ip,
        )

        # Make the request_id available to handlers via request.state
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request_failed",
                http_query=http_query,
                http_duration_ms=duration_ms,
                user_agent=user_agent,
                error_type=type(exc).__name__,
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response_size = response.headers.get("content-length")

        logger.info(
            "request_completed",
            http_query=http_query,
            http_status=response.status_code,
            http_duration_ms=duration_ms,
            http_response_bytes=int(response_size) if response_size else None,
            user_agent=user_agent,
        )

        # Echo the request ID back so clients can correlate
        response.headers["X-Request-ID"] = request_id

        structlog.contextvars.clear_contextvars()
        return response
