"""Coach service — orchestrates coaches + class-coach links + payroll.

Layer 2 — sits between the API and the repositories. Responsibilities:

- **Caller-scoped CRUD.** Every read filters by ``caller.tenant_id``; a
  foreign id returns ``CoachNotFoundError`` (mapped to 404 — we don't
  leak existence).
- **Status transitions.** ``freeze`` / ``unfreeze`` / ``cancel`` go through
  the entity's ``can_*`` guards; illegal transitions raise
  ``CoachStatusTransitionError``.
- **Link management.** A coach + a class + a role tuple is unique; the
  repository raises ``ClassCoachConflictError`` on duplicates. The
  service also enforces that the linked class belongs to the caller's
  tenant (the DB's FK only enforces existence, not tenancy).
- **invite-user.** One-shot wiring that creates a ``users`` row with
  ``role='coach'`` and links it to the coach via ``coaches.user_id``.
  Idempotent: invoking on an already-linked coach raises
  ``CoachAlreadyLinkedToUserError``.
- **Payroll math.** The interesting part — see ``earnings_for`` below
  and the pure helpers at the bottom of this file.

All service methods accept ``caller: TokenPayload`` for authz + scope.
The only helpers that don't take a caller are the pure math functions
(``fixed_prorated`` etc.) — they're tested directly without a DB.
"""

from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID as _UUID

from app.adapters.storage.postgres.class_coach.repositories import ClassCoachRepository
from app.adapters.storage.postgres.class_entry.repositories import ClassEntryRepository
from app.adapters.storage.postgres.coach.repositories import CoachRepository
from app.adapters.storage.postgres.gym_class.repositories import GymClassRepository
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.security import hash_password
from app.core.time import utcnow
from app.domain.entities.class_coach import ClassCoach, PayModel
from app.domain.entities.coach import Coach, CoachStatus
from app.domain.entities.user import Role
from app.domain.exceptions import (
    ClassCoachLinkNotFoundError,
    CoachAlreadyLinkedToUserError,
    CoachNotFoundError,
    CoachStatusTransitionError,
    GymClassNotFoundError,
    InsufficientPermissionsError,
    InvalidEarningsRangeError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload

logger = logging.getLogger(__name__)


# ── DTOs ──────────────────────────────────────────────────────────────


@dataclass
class EarningsLinkRow:
    """One row in the breakdown — per (coach, class, pay_model) slice."""

    class_id: _UUID
    class_name: str | None
    role: str
    pay_model: PayModel
    pay_amount_cents: int
    cents: int
    #: For per_attendance: number of counted entries.
    #: For per_session: distinct days with entries.
    #: For fixed: number of days in the pro-rated slice.
    unit_count: int


@dataclass
class EarningsBreakdown:
    """Earnings estimate for one coach over a date range.

    ``from_`` / ``to`` are the REQUESTED range (inclusive on both ends).
    ``effective_from`` / ``effective_to`` reflect clipping to the coach's
    lifetime (hired_at → frozen_at / cancelled_at).
    """

    coach_id: _UUID
    from_: date
    to: date
    effective_from: date | None
    effective_to: date | None
    currency: str
    total_cents: int
    by_link: list[EarningsLinkRow] = field(default_factory=list)
    by_class_cents: dict[_UUID, int] = field(default_factory=dict)
    by_pay_model_cents: dict[str, int] = field(default_factory=dict)

    @classmethod
    def zero(cls, coach_id: _UUID, from_: date, to: date, currency: str) -> EarningsBreakdown:
        return cls(
            coach_id=coach_id,
            from_=from_,
            to=to,
            effective_from=None,
            effective_to=None,
            currency=currency,
            total_cents=0,
        )


# ── Service ───────────────────────────────────────────────────────────


class CoachService:
    """Coach + class-coach CRUD + payroll estimates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CoachRepository(session)
        self._link_repo = ClassCoachRepository(session)
        self._entry_repo = ClassEntryRepository(session)
        self._class_repo = GymClassRepository(session)
        self._user_repo = UserRepository(session)

    # ── Coach CRUD ───────────────────────────────────────────────────

    async def create_coach(
        self,
        *,
        caller: TokenPayload,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        email: str | None = None,
        user_id: _UUID | None = None,
        hired_at: date | None = None,
        custom_attrs: dict[str, Any] | None = None,
    ) -> Coach:
        tenant_id = self._require_owner_in_tenant(caller)

        if user_id is not None:
            # Verify the user belongs to the same tenant before linking.
            user = await self._user_repo.find_by_id(user_id)
            if user is None or str(user.tenant_id) != str(tenant_id):
                # Refuse to leak: same 404 whether not found or cross-tenant.
                raise CoachNotFoundError(str(user_id))

        coach = await self._repo.create(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            user_id=user_id,
            hired_at=hired_at,
            custom_attrs=custom_attrs,
        )
        await self._session.commit()
        logger.info(
            "coach.created",
            extra={
                "event": "coach.created",
                "tenant_id": str(tenant_id),
                "coach_id": str(coach.id),
                "user_id": str(user_id) if user_id else None,
            },
        )
        return coach

    async def get_coach(self, *, caller: TokenPayload, coach_id: _UUID) -> Coach:
        tenant_id = self._require_tenant(caller)
        coach = await self._repo.find_by_id(coach_id)
        if coach is None or str(coach.tenant_id) != str(tenant_id):
            raise CoachNotFoundError(str(coach_id))
        # Coach users can only read their own row.
        if caller.role == Role.COACH.value:
            own = await self._repo.find_by_user_id(_UUID(caller.sub))
            if own is None or own.id != coach.id:
                raise CoachNotFoundError(str(coach_id))
        return coach

    async def list_coaches(
        self,
        *,
        caller: TokenPayload,
        status: list[CoachStatus] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Coach]:
        tenant_id = self._require_tenant(caller)
        # Coach users: return only their own row.
        if caller.role == Role.COACH.value:
            own = await self._repo.find_by_user_id(_UUID(caller.sub))
            return [own] if own else []
        return await self._repo.list_for_tenant(
            tenant_id, status=status, search=search, limit=limit, offset=offset
        )

    async def update_coach(self, *, caller: TokenPayload, coach_id: _UUID, **fields: Any) -> Coach:
        self._require_owner(caller)
        await self.get_coach(caller=caller, coach_id=coach_id)
        # Strip fields that only the state-transition methods should touch.
        fields.pop("status", None)
        fields.pop("frozen_at", None)
        fields.pop("cancelled_at", None)
        updated = await self._repo.update(coach_id, **fields)
        await self._session.commit()
        return updated

    # ── Status transitions ───────────────────────────────────────────

    async def freeze_coach(self, *, caller: TokenPayload, coach_id: _UUID) -> Coach:
        self._require_owner(caller)
        coach = await self.get_coach(caller=caller, coach_id=coach_id)
        if not coach.can_freeze():
            raise CoachStatusTransitionError(str(coach_id), coach.status.value, "freeze")
        updated = await self._repo.freeze(coach_id, frozen_at=utcnow())
        await self._session.commit()
        self._log_status_change(coach, updated, caller)
        return updated

    async def unfreeze_coach(self, *, caller: TokenPayload, coach_id: _UUID) -> Coach:
        self._require_owner(caller)
        coach = await self.get_coach(caller=caller, coach_id=coach_id)
        if not coach.can_unfreeze():
            raise CoachStatusTransitionError(str(coach_id), coach.status.value, "unfreeze")
        updated = await self._repo.unfreeze(coach_id)
        await self._session.commit()
        self._log_status_change(coach, updated, caller)
        return updated

    async def cancel_coach(self, *, caller: TokenPayload, coach_id: _UUID) -> Coach:
        self._require_owner(caller)
        coach = await self.get_coach(caller=caller, coach_id=coach_id)
        if not coach.can_cancel():
            raise CoachStatusTransitionError(str(coach_id), coach.status.value, "cancel")
        updated = await self._repo.cancel(coach_id, cancelled_at=utcnow())
        await self._session.commit()
        self._log_status_change(coach, updated, caller)
        return updated

    async def invite_user(
        self,
        *,
        caller: TokenPayload,
        coach_id: _UUID,
        email: str,
        password: str,
    ) -> Coach:
        """Create a ``users`` row with role='coach' and link it.

        Idempotent-ish: raises if the coach already has a user. Doesn't
        expose the created user; the returned Coach is sufficient for
        the UI (plus the email + one-time password it already has).
        """
        self._require_owner(caller)
        tenant_id = self._require_tenant(caller)
        coach = await self.get_coach(caller=caller, coach_id=coach_id)
        if coach.user_id is not None:
            raise CoachAlreadyLinkedToUserError(str(coach_id))

        new_user = await self._user_repo.create(
            email=email,
            password_hash=hash_password(password),
            role=Role.COACH,
            tenant_id=tenant_id,
            first_name=coach.first_name,
            last_name=coach.last_name,
            phone=coach.phone,
        )
        linked = await self._repo.link_user(coach_id, new_user.id)
        await self._session.commit()
        logger.info(
            "coach.user_linked",
            extra={
                "event": "coach.user_linked",
                "tenant_id": str(tenant_id),
                "coach_id": str(coach_id),
                "user_id": str(new_user.id),
            },
        )
        return linked

    # ── Class-coach links ────────────────────────────────────────────

    async def assign_to_class(
        self,
        *,
        caller: TokenPayload,
        class_id: _UUID,
        coach_id: _UUID,
        role: str,
        is_primary: bool,
        pay_model: PayModel,
        pay_amount_cents: int,
        weekdays: list[str],
        starts_on: date | None = None,
        ends_on: date | None = None,
    ) -> ClassCoach:
        self._require_owner(caller)
        tenant_id = self._require_tenant(caller)

        # Cross-tenant guard on both sides of the link. ``get_coach`` raises
        # ``CoachNotFoundError`` (→ 404) if the coach isn't in this tenant,
        # so we call it purely for the side effect (the return value is
        # unused — the class-coach repo only needs the id).
        await self.get_coach(caller=caller, coach_id=coach_id)
        cls = await self._class_repo.find_by_id(class_id)
        if cls is None or str(cls.tenant_id) != str(tenant_id):
            raise GymClassNotFoundError(str(class_id))

        link = await self._link_repo.create(
            tenant_id=tenant_id,
            class_id=class_id,
            coach_id=coach_id,
            role=role,
            is_primary=is_primary,
            pay_model=pay_model,
            pay_amount_cents=pay_amount_cents,
            weekdays=weekdays,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        await self._session.commit()
        logger.info(
            "coach.class_assigned",
            extra={
                "event": "coach.class_assigned",
                "tenant_id": str(tenant_id),
                "coach_id": str(coach_id),
                "class_id": str(class_id),
                "role": role,
                "pay_model": pay_model.value,
                "pay_amount_cents": pay_amount_cents,
                "weekdays": weekdays,
            },
        )
        return link

    async def update_link(
        self, *, caller: TokenPayload, link_id: _UUID, **fields: Any
    ) -> ClassCoach:
        self._require_owner(caller)
        tenant_id = self._require_tenant(caller)
        link = await self._link_repo.find_by_id(link_id)
        if link is None or str(link.tenant_id) != str(tenant_id):
            raise ClassCoachLinkNotFoundError(str(link_id))
        updated = await self._link_repo.update(link_id, **fields)
        await self._session.commit()
        return updated

    async def remove_link(self, *, caller: TokenPayload, link_id: _UUID) -> None:
        self._require_owner(caller)
        tenant_id = self._require_tenant(caller)
        link = await self._link_repo.find_by_id(link_id)
        if link is None or str(link.tenant_id) != str(tenant_id):
            raise ClassCoachLinkNotFoundError(str(link_id))
        await self._link_repo.delete(link_id)
        await self._session.commit()

    async def list_coaches_for_class(
        self, *, caller: TokenPayload, class_id: _UUID, only_current: bool = False
    ) -> list[ClassCoach]:
        tenant_id = self._require_tenant(caller)
        return await self._link_repo.list_for_class(tenant_id, class_id, only_current=only_current)

    async def list_classes_for_coach(
        self, *, caller: TokenPayload, coach_id: _UUID, only_current: bool = False
    ) -> list[ClassCoach]:
        tenant_id = self._require_tenant(caller)
        # Ensures scoping + coach-user-reads-own check.
        await self.get_coach(caller=caller, coach_id=coach_id)
        return await self._link_repo.list_for_coach(tenant_id, coach_id, only_current=only_current)

    # ── Earnings math (the interesting part) ─────────────────────────

    async def earnings_for(
        self,
        *,
        caller: TokenPayload,
        coach_id: _UUID,
        from_: date,
        to: date,
    ) -> EarningsBreakdown:
        """Payroll estimate for the coach over [from_, to] (inclusive).

        Clip the window to the coach's lifetime (hired → frozen/cancelled),
        then for each active (coach, class) link compute pay according to
        the link's ``pay_model``. Sum across links.
        """
        if to < from_:
            raise InvalidEarningsRangeError(f"to ({to}) must be >= from ({from_})")
        coach = await self.get_coach(caller=caller, coach_id=coach_id)
        tenant_id = _UUID(caller.tenant_id) if caller.tenant_id else coach.tenant_id
        currency = await self._tenant_currency(tenant_id)

        # Clip to coach lifetime.
        eff_from, eff_to = _coach_effective_window(coach, from_, to)
        if eff_from is None or eff_to is None or eff_to < eff_from:
            bd = EarningsBreakdown.zero(coach_id, from_, to, currency)
            logger.info(
                "coach.earnings_queried",
                extra={
                    "event": "coach.earnings_queried",
                    "tenant_id": str(tenant_id),
                    "coach_id": str(coach_id),
                    "from": from_.isoformat(),
                    "to": to.isoformat(),
                    "total_cents": 0,
                },
            )
            return bd

        links = await self._link_repo.list_active_links_for_coach_in_range(
            tenant_id, coach_id, eff_from, eff_to
        )
        total = 0
        rows: list[EarningsLinkRow] = []
        by_class: dict[_UUID, int] = defaultdict(int)
        by_pm: dict[str, int] = defaultdict(int)

        class_names = await self._class_names_map(tenant_id, [link.class_id for link in links])

        for link in links:
            span_from = max(eff_from, link.starts_on)
            span_to = min(eff_to, link.ends_on or eff_to)
            if span_to < span_from:
                continue

            cents, unit = await self._pay_for_link(
                tenant_id=tenant_id,
                link=link,
                span_from=span_from,
                span_to=span_to,
            )
            total += cents
            by_class[link.class_id] += cents
            by_pm[link.pay_model.value] += cents
            rows.append(
                EarningsLinkRow(
                    class_id=link.class_id,
                    class_name=class_names.get(link.class_id),
                    role=link.role,
                    pay_model=link.pay_model,
                    pay_amount_cents=link.pay_amount_cents,
                    cents=cents,
                    unit_count=unit,
                )
            )

        bd = EarningsBreakdown(
            coach_id=coach_id,
            from_=from_,
            to=to,
            effective_from=eff_from,
            effective_to=eff_to,
            currency=currency,
            total_cents=total,
            by_link=rows,
            by_class_cents=dict(by_class),
            by_pay_model_cents=dict(by_pm),
        )
        logger.info(
            "coach.earnings_queried",
            extra={
                "event": "coach.earnings_queried",
                "tenant_id": str(tenant_id),
                "coach_id": str(coach_id),
                "from": from_.isoformat(),
                "to": to.isoformat(),
                "total_cents": total,
            },
        )
        return bd

    async def earnings_summary(
        self, *, caller: TokenPayload, from_: date, to: date
    ) -> list[EarningsBreakdown]:
        """All coaches in the tenant, one breakdown each. Used by the
        owner dashboard's 'total payroll this month' widget."""
        self._require_owner(caller)
        tenant_id = self._require_tenant(caller)

        coaches = await self._repo.list_for_tenant(
            tenant_id,
            status=[CoachStatus.ACTIVE, CoachStatus.FROZEN],
            limit=500,
        )
        return [
            await self.earnings_for(caller=caller, coach_id=c.id, from_=from_, to=to)
            for c in coaches
        ]

    # ── Private: pay computation per link ────────────────────────────

    async def _pay_for_link(
        self,
        *,
        tenant_id: _UUID,
        link: ClassCoach,
        span_from: date,
        span_to: date,
    ) -> tuple[int, int]:
        """Return ``(cents, unit_count)`` for one (coach, class) link
        clipped to [span_from, span_to]."""
        if link.pay_model == PayModel.FIXED:
            cents = fixed_prorated(link.pay_amount_cents, span_from, span_to)
            units = (span_to - span_from).days + 1
            return cents, units

        since = _datetime_start_of_day_utc(span_from)
        until = _datetime_start_of_day_utc(span_to + timedelta(days=1))

        if link.pay_model == PayModel.PER_SESSION:
            days = await self._entry_repo.count_distinct_days_for_coach_class(
                tenant_id=tenant_id,
                coach_id=link.coach_id,
                class_id=link.class_id,
                since=since,
                until=until,
            )
            return days * link.pay_amount_cents, days

        if link.pay_model == PayModel.PER_ATTENDANCE:
            n = await self._entry_repo.count_effective_for_coach_class(
                tenant_id=tenant_id,
                coach_id=link.coach_id,
                class_id=link.class_id,
                since=since,
                until=until,
            )
            return n * link.pay_amount_cents, n

        return 0, 0

    # ── Small helpers ────────────────────────────────────────────────

    async def _tenant_currency(self, tenant_id: _UUID) -> str:
        from app.adapters.storage.postgres.tenant.repositories import TenantRepository

        tenant = await TenantRepository(self._session).find_by_id(tenant_id)
        return tenant.currency if tenant else "ILS"

    async def _class_names_map(self, tenant_id: _UUID, class_ids: list[_UUID]) -> dict[_UUID, str]:
        """Batch lookup of class names for the earnings breakdown. Small
        N (few classes per coach) so one query-per-class is fine."""
        result: dict[_UUID, str] = {}
        for cid in set(class_ids):
            cls = await self._class_repo.find_by_id(cid)
            if cls is not None and str(cls.tenant_id) == str(tenant_id):
                result[cid] = cls.name
        return result

    def _log_status_change(self, before: Coach, after: Coach, caller: TokenPayload) -> None:
        logger.info(
            "coach.status_changed",
            extra={
                "event": "coach.status_changed",
                "tenant_id": str(after.tenant_id),
                "coach_id": str(after.id),
                "from": before.status.value,
                "to": after.status.value,
                "by": caller.sub,
            },
        )

    # ── Role / tenant gates ──────────────────────────────────────────

    @staticmethod
    def _require_tenant(caller: TokenPayload) -> _UUID:
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return _UUID(caller.tenant_id)

    @staticmethod
    def _require_owner(caller: TokenPayload) -> None:
        if caller.role not in (Role.OWNER.value, Role.SUPER_ADMIN.value):
            raise InsufficientPermissionsError()

    def _require_owner_in_tenant(self, caller: TokenPayload) -> _UUID:
        self._require_owner(caller)
        return self._require_tenant(caller)


# ── Pure helpers (tested without a DB) ────────────────────────────────


def fixed_prorated(monthly_cents: int, span_from: date, span_to: date) -> int:
    """Prorate a monthly salary over a span that may cross month
    boundaries.

    Rule: for each calendar month touched by [span_from, span_to],
    ``overlap_days / days_in_that_month`` times ``monthly_cents`` is
    added to the total. Rounded to cents at the end (banker's rounding).

    Examples:
    - Full month (May 1–31) for 3000 ILS/mo  → 300000 cents
    - Half month (May 1–15) for 3000 ILS/mo  → 300000 * 15 / 31 ≈ 145161
    - Cross-month (Apr 20 – May 10) for 3000 → (11/30 + 10/31) * 300000

    Banker's rounding (``ROUND_HALF_EVEN``) to match accounting conventions.
    """
    from decimal import ROUND_HALF_EVEN, Decimal

    if span_to < span_from:
        return 0
    total = Decimal(0)
    cursor = span_from.replace(day=1)
    while cursor <= span_to:
        days_in_month = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = cursor.replace(day=days_in_month)
        ov_start = max(cursor, span_from)
        ov_end = min(month_end, span_to)
        overlap_days = (ov_end - ov_start).days + 1
        if overlap_days > 0:
            total += Decimal(monthly_cents) * Decimal(overlap_days) / Decimal(days_in_month)
        cursor = _first_of_next_month(cursor)
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _first_of_next_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _datetime_start_of_day_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _coach_effective_window(coach: Coach, from_: date, to: date) -> tuple[date | None, date | None]:
    """Clip [from_, to] to the coach's active lifetime.

    - hired_at pushes the start forward.
    - cancelled_at (terminal) pushes the end backward — earnings stop
      on cancellation day.
    - frozen_at pushes the end backward by ONE day (earnings stop the
      day before the freeze). A frozen coach gets no new accrual.

    Returns (None, None) if the window falls outside the coach's
    lifetime entirely.
    """
    start = max(from_, coach.hired_at)
    end = to

    if coach.cancelled_at is not None:
        end = min(end, coach.cancelled_at.date())
    if coach.frozen_at is not None:
        end = min(end, coach.frozen_at.date() - timedelta(days=1))

    if end < start:
        return None, None
    return start, end


__all__ = [
    "CoachService",
    "EarningsBreakdown",
    "EarningsLinkRow",
    "fixed_prorated",
    "_coach_effective_window",
    "_first_of_next_month",
]
