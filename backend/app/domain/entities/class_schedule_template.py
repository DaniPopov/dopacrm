"""Pydantic domain entity for schedule templates.

A template is the recurring rule the owner creates once — "boxing,
Sun+Tue, 18:00–19:00, head coach David, assistant Yoni." The backend
materializes it into concrete ``class_sessions`` rows on create +
nightly via the Celery beat job.

Editing a template triggers re-materialization of future non-customized
sessions. Cancelled / customized sessions stay frozen.
"""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.entities.class_coach import WEEKDAYS, weekday_code


class ClassScheduleTemplate(BaseModel):
    """Recurring rule that spawns ``class_sessions`` rows."""

    id: UUID
    tenant_id: UUID
    class_id: UUID

    weekdays: list[str] = Field(
        description="Lowercase 3-letter codes ('sun'..'sat'). Cannot be empty."
    )
    start_time: time
    end_time: time

    head_coach_id: UUID
    assistant_coach_id: UUID | None = None

    starts_on: date
    ends_on: date | None = None
    is_active: bool = True

    created_at: datetime
    updated_at: datetime

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[str]) -> list[str]:
        if not v:
            msg = "weekdays cannot be empty — template needs at least one day"
            raise ValueError(msg)
        for w in v:
            if w not in WEEKDAYS:
                msg = f"invalid weekday code: {w!r}"
                raise ValueError(msg)
        if len(set(v)) != len(v):
            msg = "duplicate weekday codes"
            raise ValueError(msg)
        return v

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            msg = "end_time must be after start_time"
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
        """Does this template apply on the given date?

        Three conditions:
        1. ``d`` falls in [starts_on, ends_on] (or starts_on.. if
           ends_on is None).
        2. The template is active.
        3. ``d``'s weekday is one of ``weekdays``.
        """
        if not self.is_active:
            return False
        if d < self.starts_on:
            return False
        if self.ends_on is not None and d > self.ends_on:
            return False
        return weekday_code(d) in self.weekdays
