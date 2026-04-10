"""Centralized timezone handling.

Two timezone contexts:

1. **System time (Israel)** — the platform operator works from Israel.
   Used for: logging, internal dashboards, admin-facing timestamps.

2. **Tenant time** — each gym has its own timezone stored in its tenant
   record. Used for: member-facing display, "today" calculations,
   reports scoped to the gym's local day.

Internal storage and inter-service communication always use **UTC** —
convert at the boundaries.

    from app.core.time import now, utcnow, to_system_tz

    # Logging / admin display — Israel-aware
    logger.info("session_started", at=now())

    # Database storage — UTC
    member.created_at = utcnow()

    # Converting a UTC datetime for admin display
    display_time = to_system_tz(member.created_at)
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

#: System timezone — operator's working timezone (Israel).
SYSTEM_TZ = ZoneInfo("Asia/Jerusalem")


def now() -> datetime:
    """Return the current time as a tz-aware datetime in system (Israel) time."""
    return datetime.now(SYSTEM_TZ)


def utcnow() -> datetime:
    """Return the current time as a tz-aware UTC datetime.

    Prefer this for: database columns, message payloads, anything stored
    or sent over the wire.
    """
    return datetime.now(UTC)


def to_system_tz(dt: datetime) -> datetime:
    """Convert a datetime to system (Israel) time.

    Naive datetimes are assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(SYSTEM_TZ)


def to_tenant_tz(dt: datetime, tz_name: str) -> datetime:
    """Convert a datetime to a tenant's local time.

    Args:
        dt: The datetime to convert. Naive datetimes are assumed UTC.
        tz_name: IANA timezone name from the tenant record (e.g. 'Europe/Sofia').
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(tz_name))


def to_utc(dt: datetime) -> datetime:
    """Convert a datetime to UTC.

    Naive datetimes are assumed to be in system (Israel) time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SYSTEM_TZ)
    return dt.astimezone(UTC)
