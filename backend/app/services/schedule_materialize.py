"""Pure materialization helpers.

Turning a template + a date range into concrete session timestamps is
pure math — no DB access, no side effects. Kept separate from the
ScheduleService so unit tests can exercise leap years, DST, weekday
filters etc. without booting Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.domain.entities.class_schedule_template import ClassScheduleTemplate


#: Default tenant timezone. When tenants support multi-region, this
#: becomes a per-tenant lookup via ``tenant.timezone``.
DEFAULT_TENANT_TZ = ZoneInfo("Asia/Jerusalem")


def materialize_dates(
    template: ClassScheduleTemplate,
    from_: date,
    to: date,
) -> list[date]:
    """Return every date in ``[from_, to]`` that the template covers.

    Inclusive on both ends. Clipped to ``template.starts_on`` and
    ``template.ends_on``. Respects the template's ``weekdays`` filter
    and ``is_active`` flag.

    Pure — no side effects. Ideal for unit testing DST / leap years /
    weekday math without a DB.
    """
    if to < from_:
        return []
    if not template.is_active:
        return []

    start = max(from_, template.starts_on)
    end = to if template.ends_on is None else min(to, template.ends_on)
    if end < start:
        return []

    out: list[date] = []
    cursor = start
    while cursor <= end:
        if template.covers(cursor):
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def session_timestamps(
    template: ClassScheduleTemplate,
    session_date: date,
    tenant_tz: ZoneInfo = DEFAULT_TENANT_TZ,
) -> tuple[datetime, datetime]:
    """Combine ``(date, template.start_time, template.end_time)`` in
    the tenant's timezone → UTC ``(starts_at, ends_at)``.

    DST handled naturally — ``replace(tzinfo=tenant_tz)`` on a naive
    local time + ``.astimezone(UTC)`` yields the correct UTC instant
    even on fall-back / spring-forward transitions.

    Returned timestamps are timezone-aware (tzinfo=UTC).
    """
    local_start = datetime.combine(session_date, template.start_time).replace(tzinfo=tenant_tz)
    local_end = datetime.combine(session_date, template.end_time).replace(tzinfo=tenant_tz)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


__all__ = ["DEFAULT_TENANT_TZ", "materialize_dates", "session_timestamps"]
