"""Schedule service — templates, materialization, sessions, bulk edits.

Layer 2 — orchestrates the template → materialized sessions pipeline,
owner-driven edits (cancel, swap coach, shift time), and the bulk
range action for the coach-vacation scenario.

Every mutation + read guards on ``is_feature_enabled(tenant, "schedule")``
before doing anything. Tenant scope is enforced by re-reading each
resource's ``tenant_id`` and comparing to ``caller.tenant_id`` — the
standard pattern. Structlog events mirror `docs/features/schedule.md`
§"Observability".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID as _UUID

from app.adapters.storage.postgres.class_schedule_template.repositories import (
    ClassScheduleTemplateRepository,
)
from app.adapters.storage.postgres.class_session.repositories import (
    ClassSessionRepository,
)
from app.adapters.storage.postgres.coach.repositories import CoachRepository
from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.core.feature_flags import is_feature_enabled
from app.core.time import utcnow
from app.domain.entities.class_schedule_template import ClassScheduleTemplate
from app.domain.entities.class_session import ClassSession, SessionStatus
from app.domain.entities.user import Role
from app.domain.exceptions import (
    ClassScheduleTemplateNotFoundError,
    ClassSessionNotFoundError,
    CoachNotFoundError,
    FeatureDisabledError,
    GymClassNotFoundError,
    InsufficientPermissionsError,
    InvalidBulkRangeError,
    SessionStatusTransitionError,
)
from app.services.schedule_materialize import (
    DEFAULT_TENANT_TZ,
    materialize_dates,
    session_timestamps,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload

logger = logging.getLogger(__name__)

#: How many weeks of future sessions the service materializes on
#: template create + the nightly beat job extends to. Keep in sync with
#: docs/features/schedule.md §D.
DEFAULT_HORIZON_WEEKS: int = 8


# ── DTOs ──────────────────────────────────────────────────────────────


@dataclass
class BulkActionResult:
    """Summary of a bulk range action."""

    action: str  # "cancel" | "swap_coach"
    affected_ids: list[_UUID]
    cancelled_count: int = 0
    swapped_count: int = 0


# ── Service ───────────────────────────────────────────────────────────


class ScheduleService:
    """Templates + materialized sessions + bulk edits + attribution helper."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tpl_repo = ClassScheduleTemplateRepository(session)
        self._sess_repo = ClassSessionRepository(session)
        self._class_repo = GymClassRepository(session)
        self._coach_repo = CoachRepository(session)
        self._tenant_repo = TenantRepository(session)

    # ── Template CRUD ────────────────────────────────────────────────

    async def create_template(
        self,
        *,
        caller: TokenPayload,
        class_id: _UUID,
        weekdays: list[str],
        start_time: time,
        end_time: time,
        head_coach_id: _UUID,
        assistant_coach_id: _UUID | None = None,
        starts_on: date | None = None,
        ends_on: date | None = None,
    ) -> ClassScheduleTemplate:
        """Create a template and materialize the first ``DEFAULT_HORIZON_WEEKS``
        weeks of sessions."""
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)

        # Validate class + coaches belong to this tenant.
        await self._assert_class_in_tenant(class_id, tenant_id)
        await self._assert_coach_in_tenant(head_coach_id, tenant_id)
        if assistant_coach_id is not None:
            await self._assert_coach_in_tenant(assistant_coach_id, tenant_id)

        tpl = await self._tpl_repo.create(
            tenant_id=tenant_id,
            class_id=class_id,
            weekdays=weekdays,
            start_time=start_time,
            end_time=end_time,
            head_coach_id=head_coach_id,
            assistant_coach_id=assistant_coach_id,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        await self._session.commit()

        logger.info(
            "schedule.template_created",
            extra={
                "event": "schedule.template_created",
                "tenant_id": str(tenant_id),
                "template_id": str(tpl.id),
                "class_id": str(class_id),
                "weekdays": weekdays,
            },
        )

        # Materialize immediately so the owner sees sessions on the
        # week view without waiting for the nightly beat job.
        count = await self._materialize_horizon(tpl)
        logger.info(
            "schedule.horizon_extended",
            extra={
                "event": "schedule.horizon_extended",
                "tenant_id": str(tenant_id),
                "template_id": str(tpl.id),
                "sessions_created": count,
            },
        )
        return tpl

    async def get_template(
        self, *, caller: TokenPayload, template_id: _UUID
    ) -> ClassScheduleTemplate:
        tenant_id = await self._require_schedule_enabled(caller)
        tpl = await self._tpl_repo.find_by_id(template_id)
        if tpl is None or str(tpl.tenant_id) != str(tenant_id):
            raise ClassScheduleTemplateNotFoundError(str(template_id))
        return tpl

    async def list_templates(
        self,
        *,
        caller: TokenPayload,
        class_id: _UUID | None = None,
        only_active: bool = False,
    ) -> list[ClassScheduleTemplate]:
        tenant_id = await self._require_schedule_enabled(caller)
        return await self._tpl_repo.list_for_tenant(
            tenant_id, class_id=class_id, only_active=only_active
        )

    async def update_template(
        self,
        *,
        caller: TokenPayload,
        template_id: _UUID,
        **fields: Any,
    ) -> ClassScheduleTemplate:
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)
        tpl = await self.get_template(caller=caller, template_id=template_id)

        # Disallow mutating tenant_id / class_id via PATCH. Class
        # change = create new template + deactivate old.
        fields.pop("tenant_id", None)
        fields.pop("class_id", None)

        updated = await self._tpl_repo.update(template_id, **fields)
        assert updated is not None

        # Re-materialize future non-customized sessions with the new
        # template values. Past sessions stay frozen as payroll history.
        await self._rematerialize_future(updated)
        await self._session.commit()

        logger.info(
            "schedule.template_edited",
            extra={
                "event": "schedule.template_edited",
                "tenant_id": str(tenant_id),
                "template_id": str(template_id),
                "diff": fields,
            },
        )
        return updated

    async def deactivate_template(
        self, *, caller: TokenPayload, template_id: _UUID
    ) -> ClassScheduleTemplate:
        """Soft-delete — is_active=False. Cancel future non-customized
        sessions so the calendar is clean; customized sessions (cancelled
        or substituted) stay as-is."""
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)
        tpl = await self.get_template(caller=caller, template_id=template_id)

        # Cancel future non-customized sessions.
        now = utcnow()
        future = await self._sess_repo.list_for_template_future(tpl.id, now)
        cancelled_ids: list[_UUID] = []
        for s in future:
            if s.status != SessionStatus.SCHEDULED or s.is_customized:
                continue
            await self._sess_repo.update(
                s.id,
                status=SessionStatus.CANCELLED,
                cancelled_at=now,
                cancelled_by=self._caller_uuid(caller),
                cancellation_reason="template deactivated",
            )
            cancelled_ids.append(s.id)

        deactivated = await self._tpl_repo.deactivate(template_id)
        await self._session.commit()

        logger.info(
            "schedule.template_deactivated",
            extra={
                "event": "schedule.template_deactivated",
                "tenant_id": str(tenant_id),
                "template_id": str(template_id),
                "sessions_cancelled": len(cancelled_ids),
            },
        )
        assert deactivated is not None
        return deactivated

    # ── Session CRUD ─────────────────────────────────────────────────

    async def create_adhoc_session(
        self,
        *,
        caller: TokenPayload,
        class_id: _UUID,
        starts_at: datetime,
        ends_at: datetime,
        head_coach_id: _UUID | None,
        assistant_coach_id: _UUID | None = None,
        notes: str | None = None,
    ) -> ClassSession:
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)

        await self._assert_class_in_tenant(class_id, tenant_id)
        if head_coach_id is not None:
            await self._assert_coach_in_tenant(head_coach_id, tenant_id)
        if assistant_coach_id is not None:
            await self._assert_coach_in_tenant(assistant_coach_id, tenant_id)

        sess = await self._sess_repo.create(
            tenant_id=tenant_id,
            class_id=class_id,
            template_id=None,
            starts_at=starts_at,
            ends_at=ends_at,
            head_coach_id=head_coach_id,
            assistant_coach_id=assistant_coach_id,
            is_customized=True,  # ad-hoc is always "owner-placed"
            notes=notes,
        )
        await self._session.commit()

        logger.info(
            "schedule.session_created_adhoc",
            extra={
                "event": "schedule.session_created_adhoc",
                "tenant_id": str(tenant_id),
                "session_id": str(sess.id),
                "class_id": str(class_id),
                "head_coach_id": str(head_coach_id) if head_coach_id else None,
                "by": caller.sub,
            },
        )
        return sess

    async def get_session(
        self, *, caller: TokenPayload, session_id: _UUID
    ) -> ClassSession:
        tenant_id = await self._require_schedule_enabled(caller)
        sess = await self._sess_repo.find_by_id(session_id)
        if sess is None or str(sess.tenant_id) != str(tenant_id):
            raise ClassSessionNotFoundError(str(session_id))
        return sess

    async def list_sessions(
        self,
        *,
        caller: TokenPayload,
        from_: datetime,
        to: datetime,
        class_id: _UUID | None = None,
        coach_id: _UUID | None = None,
        include_cancelled: bool = True,
    ) -> list[ClassSession]:
        tenant_id = await self._require_schedule_enabled(caller)
        # Coach users see only their own sessions.
        if caller.role == Role.COACH.value:
            own = await self._coach_repo.find_by_user_id(_UUID(caller.sub))
            if own is None:
                return []
            coach_id = own.id
        return await self._sess_repo.list_for_range(
            tenant_id,
            from_,
            to,
            class_id=class_id,
            coach_id=coach_id,
            include_cancelled=include_cancelled,
        )

    async def update_session(
        self,
        *,
        caller: TokenPayload,
        session_id: _UUID,
        head_coach_id: _UUID | None = None,
        assistant_coach_id: _UUID | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        notes: str | None = None,
        _skip_mark_customized: bool = False,
    ) -> ClassSession:
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)
        sess = await self.get_session(caller=caller, session_id=session_id)
        if sess.status != SessionStatus.SCHEDULED:
            raise SessionStatusTransitionError(
                str(session_id), sess.status.value, "edit"
            )

        fields: dict[str, Any] = {}
        if head_coach_id is not None:
            await self._assert_coach_in_tenant(head_coach_id, tenant_id)
            fields["head_coach_id"] = head_coach_id
        if assistant_coach_id is not None:
            await self._assert_coach_in_tenant(assistant_coach_id, tenant_id)
            fields["assistant_coach_id"] = assistant_coach_id
        if starts_at is not None:
            fields["starts_at"] = starts_at
        if ends_at is not None:
            fields["ends_at"] = ends_at
        if notes is not None:
            fields["notes"] = notes

        if not fields:
            return sess

        fields["is_customized"] = True  # any edit customizes
        updated = await self._sess_repo.update(session_id, **fields)
        await self._session.commit()

        # Log the diff that matters for audit.
        if head_coach_id is not None and head_coach_id != sess.head_coach_id:
            logger.info(
                "schedule.session_coach_swapped",
                extra={
                    "event": "schedule.session_coach_swapped",
                    "tenant_id": str(tenant_id),
                    "session_id": str(session_id),
                    "old_coach": str(sess.head_coach_id) if sess.head_coach_id else None,
                    "new_coach": str(head_coach_id),
                    "by": caller.sub,
                },
            )
        if starts_at is not None or ends_at is not None:
            logger.info(
                "schedule.session_time_edited",
                extra={
                    "event": "schedule.session_time_edited",
                    "tenant_id": str(tenant_id),
                    "session_id": str(session_id),
                    "old_start": sess.starts_at.isoformat(),
                    "new_start": (starts_at or sess.starts_at).isoformat(),
                    "by": caller.sub,
                },
            )
        assert updated is not None
        return updated

    async def cancel_session(
        self,
        *,
        caller: TokenPayload,
        session_id: _UUID,
        reason: str | None = None,
    ) -> ClassSession:
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)
        sess = await self.get_session(caller=caller, session_id=session_id)
        if not sess.can_cancel():
            raise SessionStatusTransitionError(
                str(session_id), sess.status.value, "cancel"
            )

        now = utcnow()
        updated = await self._sess_repo.update(
            session_id,
            status=SessionStatus.CANCELLED,
            cancelled_at=now,
            cancelled_by=self._caller_uuid(caller),
            cancellation_reason=reason,
            is_customized=True,
        )
        await self._session.commit()

        logger.info(
            "schedule.session_cancelled",
            extra={
                "event": "schedule.session_cancelled",
                "tenant_id": str(tenant_id),
                "session_id": str(session_id),
                "by": caller.sub,
                "reason": reason,
            },
        )
        assert updated is not None
        return updated

    # ── Bulk action ──────────────────────────────────────────────────

    async def bulk_action(
        self,
        *,
        caller: TokenPayload,
        class_id: _UUID,
        from_date: date,
        to_date: date,
        action: str,  # "cancel" | "swap_coach"
        new_coach_id: _UUID | None = None,
        reason: str | None = None,
    ) -> BulkActionResult:
        """Apply one action to every scheduled session in a range.

        Single transaction, single log event with all affected IDs."""
        tenant_id = await self._require_schedule_enabled(caller)
        self._require_owner(caller)

        if to_date < from_date:
            raise InvalidBulkRangeError(
                f"to_date ({to_date}) must be >= from_date ({from_date})"
            )
        if (to_date - from_date).days > 366:
            raise InvalidBulkRangeError("bulk range > 1 year is not allowed")

        await self._assert_class_in_tenant(class_id, tenant_id)
        if action == "swap_coach":
            if new_coach_id is None:
                raise InvalidBulkRangeError(
                    "swap_coach requires new_coach_id"
                )
            await self._assert_coach_in_tenant(new_coach_id, tenant_id)
        elif action != "cancel":
            raise InvalidBulkRangeError(
                f"unknown action {action!r}; use 'cancel' or 'swap_coach'"
            )

        # Convert date range to UTC datetime boundaries (inclusive on both ends).
        from_dt = datetime.combine(from_date, time.min, tzinfo=UTC)
        to_dt = datetime.combine(
            to_date + timedelta(days=1), time.min, tzinfo=UTC
        )
        targets = await self._sess_repo.list_in_range_for_class(
            tenant_id=tenant_id,
            class_id=class_id,
            from_date=from_dt,
            to_date=to_dt,
            scheduled_only=True,
        )

        now = utcnow()
        caller_id = self._caller_uuid(caller)
        affected: list[_UUID] = []
        for s in targets:
            if action == "cancel":
                await self._sess_repo.update(
                    s.id,
                    status=SessionStatus.CANCELLED,
                    cancelled_at=now,
                    cancelled_by=caller_id,
                    cancellation_reason=reason,
                    is_customized=True,
                )
            else:  # swap_coach
                await self._sess_repo.update(
                    s.id,
                    head_coach_id=new_coach_id,
                    is_customized=True,
                )
            affected.append(s.id)

        await self._session.commit()

        result = BulkActionResult(
            action=action,
            affected_ids=affected,
            cancelled_count=len(affected) if action == "cancel" else 0,
            swapped_count=len(affected) if action == "swap_coach" else 0,
        )

        logger.info(
            "schedule.bulk_action",
            extra={
                "event": "schedule.bulk_action",
                "tenant_id": str(tenant_id),
                "action": action,
                "class_id": str(class_id),
                "range": [from_date.isoformat(), to_date.isoformat()],
                "affected_session_ids": [str(i) for i in affected],
                "new_coach_id": str(new_coach_id) if new_coach_id else None,
                "by": caller.sub,
            },
        )
        return result

    # ── Attribution helper (called by AttendanceService) ─────────────

    async def find_active_session_for_entry(
        self,
        *,
        tenant_id: _UUID,
        class_id: _UUID,
        at: datetime,
    ) -> ClassSession | None:
        """Caller-less helper used by the attendance attribution hook.

        Safe to call without the feature check — caller has already
        decided to consult it (the attendance service branches on
        `is_feature_enabled`)."""
        return await self._sess_repo.find_active_for_class(tenant_id, class_id, at)

    # ── Beat-job helper ──────────────────────────────────────────────

    async def extend_horizon_for_template(
        self, template: ClassScheduleTemplate
    ) -> int:
        """Called by the nightly beat task. Returns the number of new
        sessions created."""
        return await self._materialize_horizon(template)

    # ── Private ──────────────────────────────────────────────────────

    async def _materialize_horizon(
        self, tpl: ClassScheduleTemplate
    ) -> int:
        """Idempotent materialization up to today + DEFAULT_HORIZON_WEEKS.
        Returns count of new sessions actually inserted."""
        today = date.today()
        horizon_end = today + timedelta(weeks=DEFAULT_HORIZON_WEEKS)
        dates = materialize_dates(tpl, from_=today, to=horizon_end)

        created = 0
        for d in dates:
            starts_at, ends_at = session_timestamps(tpl, d, DEFAULT_TENANT_TZ)
            sess = await self._sess_repo.materialize_session(
                tenant_id=tpl.tenant_id,
                class_id=tpl.class_id,
                template_id=tpl.id,
                starts_at=starts_at,
                ends_at=ends_at,
                head_coach_id=tpl.head_coach_id,
                assistant_coach_id=tpl.assistant_coach_id,
            )
            if sess is not None:
                created += 1
        # Commit so the materialized rows are visible to subsequent
        # requests. The request session dependency does NOT auto-commit;
        # closing without an explicit commit rolls back our inserts.
        await self._session.commit()
        return created

    async def _rematerialize_future(self, tpl: ClassScheduleTemplate) -> None:
        """Edit-template → update future non-customized sessions with
        the new template values. Does NOT touch cancelled or
        customized rows."""
        now = utcnow()
        future = await self._sess_repo.list_for_template_future(tpl.id, now)
        for s in future:
            if s.status != SessionStatus.SCHEDULED or s.is_customized:
                continue
            # Recompute session timestamps from the template.
            starts_at, ends_at = session_timestamps(
                tpl, s.starts_at.astimezone(DEFAULT_TENANT_TZ).date(), DEFAULT_TENANT_TZ
            )
            await self._sess_repo.update(
                s.id,
                starts_at=starts_at,
                ends_at=ends_at,
                head_coach_id=tpl.head_coach_id,
                assistant_coach_id=tpl.assistant_coach_id,
            )
        # Also extend the horizon — template weekday changes might add
        # dates that weren't materialized before.
        await self._materialize_horizon(tpl)

    # ── Cross-tenant helpers ─────────────────────────────────────────

    async def _assert_class_in_tenant(
        self, class_id: _UUID, tenant_id: _UUID
    ) -> None:
        cls = await self._class_repo.find_by_id(class_id)
        if cls is None or str(cls.tenant_id) != str(tenant_id):
            raise GymClassNotFoundError(str(class_id))

    async def _assert_coach_in_tenant(
        self, coach_id: _UUID, tenant_id: _UUID
    ) -> None:
        coach = await self._coach_repo.find_by_id(coach_id)
        if coach is None or str(coach.tenant_id) != str(tenant_id):
            raise CoachNotFoundError(str(coach_id))

    # ── Role + feature gates ─────────────────────────────────────────

    async def _require_schedule_enabled(self, caller: TokenPayload) -> _UUID:
        """Assert caller has a tenant, Schedule is ON for that tenant.
        Returns the tenant UUID for convenience."""
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        tenant_id = _UUID(caller.tenant_id)
        tenant = await self._tenant_repo.find_by_id(tenant_id)
        if tenant is None:
            # Should never happen with a valid JWT; fail closed.
            raise InsufficientPermissionsError()
        if not is_feature_enabled(tenant, "schedule"):
            raise FeatureDisabledError("schedule")
        return tenant_id

    @staticmethod
    def _require_owner(caller: TokenPayload) -> None:
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()

    @staticmethod
    def _caller_uuid(caller: TokenPayload) -> _UUID | None:
        if caller.sub is None:
            return None
        try:
            return _UUID(caller.sub)
        except (TypeError, ValueError):
            return None


__all__ = ["ScheduleService", "BulkActionResult", "DEFAULT_HORIZON_WEEKS"]
