"""Pydantic domain entity for the class ↔ coach link.

Every (coach, class) assignment carries its own pay rule: a coach can
be "head of boxing at ₪50 per attendee" AND "assistant in wrestling at
₪30 per session" on the same gym. Pay lives on the LINK, not on the
coach.

The link also carries:
- ``role`` — free-form text ("ראשי", "עוזר", "night-shift"). Owner names it.
- ``weekdays`` — which days of the week this coach teaches this class.
  Used by the attendance attribution rule (see ``crm_logic.md`` §5).
  Empty = "all days" (coach is attributed whenever a match is needed).
- ``starts_on`` / ``ends_on`` — the rate window. Rate changes = end
  the current row + insert a new one. Don't mutate ``pay_amount_cents``
  in place; it rewrites payroll history.

Weekday codes: lowercase 3-letter ``sun``..``sat``. Stored as TEXT[] in
Postgres; Python exposes them as ``list[str]``.
"""

from datetime import date
from datetime import datetime as _dt
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PayModel(StrEnum):
    """How a coach gets paid for one (class) link."""

    #: Monthly salary. Earnings queries pro-rate by day over partial months.
    FIXED = "fixed"
    #: Flat amount per distinct session the coach ran (v1 proxy:
    #: distinct days with ≥1 attributed entry in this class).
    PER_SESSION = "per_session"
    #: Flat amount per effective (undone_at IS NULL) attributed entry.
    PER_ATTENDANCE = "per_attendance"


#: Python's ``date.weekday()`` returns Monday=0 .. Sunday=6. We convert
#: to the 3-letter Sunday-indexed codes used on the link.
WEEKDAYS: tuple[str, ...] = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def weekday_code(d: date) -> str:
    """Map a date to its lowercase 3-letter weekday code.

    Sunday is index 0 (Israel's work week starts Sunday). Python's
    ``weekday()`` returns Monday=0 .. Sunday=6 — convert.
    """
    # Monday=0..Sunday=6  →  Sunday=0..Saturday=6
    return WEEKDAYS[(d.weekday() + 1) % 7]


class ClassCoach(BaseModel):
    """Link row: which coach teaches which class, how they're paid,
    on which days, over which date range."""

    id: UUID
    tenant_id: UUID
    class_id: UUID
    coach_id: UUID

    role: str = Field(default="ראשי", description="Free-form label — owner writes it.")
    is_primary: bool = Field(
        default=False,
        description=(
            "When multiple coaches teach the same class on the same weekday, "
            "the primary gets per-attendance credit. Attribution falls back "
            "to deterministic-sort if no primary is set."
        ),
    )

    pay_model: PayModel
    pay_amount_cents: int = Field(ge=0, description="Amount in tenant currency cents.")

    weekdays: list[str] = Field(
        default_factory=list,
        description="Lowercase 3-letter codes. Empty = all days.",
    )

    starts_on: date
    ends_on: date | None = None

    created_at: _dt
    updated_at: _dt

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[str]) -> list[str]:
        for w in v:
            if w not in WEEKDAYS:
                msg = f"invalid weekday code: {w!r} (expected one of {WEEKDAYS})"
                raise ValueError(msg)
        if len(set(v)) != len(v):
            msg = "duplicate weekday codes"
            raise ValueError(msg)
        return v

    @field_validator("ends_on")
    @classmethod
    def _range_valid(cls, v: date | None, info) -> date | None:
        start = info.data.get("starts_on")
        if v is not None and start is not None and v < start:
            msg = "ends_on must be on or after starts_on"
            raise ValueError(msg)
        return v

    def covers(self, d: date) -> bool:
        """True if this link applies on date d.

        Two conditions:
        1. ``d`` lies in [starts_on, ends_on] (or starts_on.. if
           ends_on is None).
        2. ``d``'s weekday matches one in ``weekdays``, or ``weekdays``
           is empty (treated as "every day").
        """
        if d < self.starts_on:
            return False
        if self.ends_on is not None and d > self.ends_on:
            return False
        if not self.weekdays:
            return True
        return weekday_code(d) in self.weekdays
