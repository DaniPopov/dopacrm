"""Structured logging setup using structlog.

JSON output by default — Promtail picks it up from Docker stdout and ships
to Loki. Set APP_LOG_FORMAT=console for human-readable colored output during
local non-Docker development.

Field schema (consistent across every log line):

    timestamp        ISO 8601 in system time (Israel), e.g. 2026-04-08T21:06:26.591+03:00
    level            debug | info | warning | error | critical
    event            short snake_case event name (e.g. "request_completed")
    logger           dotted logger name (e.g. "app.access")
    service          backend | worker | worker-beat (from APP_SERVICE_NAME env)
    env              development | staging | production (from APP_ENV)
    ... event-specific fields, ordered last (request_id, method, path, ...)

Usage:
    from app.core.logger import get_logger

    logger = get_logger(__name__)
    logger.info("user_logged_in", user_id="abc", tenant_id="acme")
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

import structlog

from app.core.time import now as system_now

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger
    from structlog.types import EventDict, Processor, WrappedLogger

_configured = False

#: Fields that always appear first, in this order.
_PRIORITY_FIELDS: tuple[str, ...] = (
    "timestamp",
    "level",
    "event",
    "logger",
    "service",
    "env",
    "request_id",
)


def _system_timestamp(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """Add a tz-aware ISO 8601 timestamp in system time (Israel).

    Output format: ``2026-04-08T21:06:26.591+03:00``
    Replaces structlog's default UTC TimeStamper so the JSON timestamp
    matches what the operator sees in Grafana / dashboards.
    """
    event_dict["timestamp"] = system_now().isoformat(timespec="milliseconds")
    return event_dict


def _add_service_context(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """Add ``service`` and ``env`` to every log line.

    Read from env vars (APP_SERVICE_NAME, APP_ENV) at log time so each
    container (backend / worker / worker-beat) self-identifies without
    needing per-container code.
    """
    event_dict.setdefault("service", os.getenv("APP_SERVICE_NAME", "backend"))
    event_dict.setdefault("env", os.getenv("APP_ENV", "development"))
    return event_dict


def _order_fields(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """Reorder fields so logs are predictable and easy to scan.

    Always-on meta fields (timestamp, level, event, logger, service, env)
    come first, in a fixed order. Everything else follows alphabetically.
    JSON renderers preserve dict insertion order, so this controls the
    on-the-wire field order.
    """
    ordered: dict[str, Any] = {}
    for key in _PRIORITY_FIELDS:
        if key in event_dict:
            ordered[key] = event_dict.pop(key)
    for key in sorted(event_dict.keys()):
        ordered[key] = event_dict[key]
    return ordered


def setup_logging() -> None:
    """Configure structlog and stdlib logging.

    Idempotent — safe to call multiple times. Reads APP_LOG_LEVEL and
    APP_LOG_FORMAT from env (json | console). Defaults to JSON so log
    aggregators (Loki, CloudWatch, etc.) can parse fields directly.
    """
    global _configured
    if _configured:
        return

    log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("APP_LOG_FORMAT", "json").lower()

    # Stdlib logging — third-party libraries (uvicorn, sqlalchemy, etc.) use this.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    # Quiet down noisy libraries.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # we have our own
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _system_timestamp,
        _add_service_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _order_fields,  # MUST be last — fixes the on-the-wire order
    ]

    if log_format == "console":
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True, sort_keys=False)
    else:
        renderer = structlog.processors.JSONRenderer(sort_keys=False)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a structlog BoundLogger.

    Calls setup_logging() on first use so callers don't have to remember to
    initialize before getting a logger.
    """
    if not _configured:
        setup_logging()
    return structlog.get_logger(name)
