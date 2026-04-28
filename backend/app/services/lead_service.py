"""Lead service — sales pipeline orchestrator.

Layer 2 — owns the leads CRUD, the pipeline state machine, the
append-only activity timeline, and the **convert** flow that creates a
real Member + first Subscription in one transaction.

Every mutation + read guards on ``is_feature_enabled(tenant, "leads")``
before doing anything. Tenant scope is enforced by re-reading each
resource's ``tenant_id`` and comparing to ``caller.tenant_id`` — the
standard pattern. Structlog events mirror ``docs/features/leads.md``
§"Observability".

Permissions:

- **owner / super_admin / sales** — full CRUD + convert.
- **staff** — read-only (so check-in staff can spot a walk-in's lead
  history when looking up an unfamiliar phone).
- **coach** — no access (gated at ``RequireFeature`` and here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID as _UUID

from app.adapters.storage.postgres.lead.repositories import LeadRepository, LostReasonRow
from app.adapters.storage.postgres.lead_activity.repositories import (
    LeadActivityRepository,
)
from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.membership_plan.repositories import (
    MembershipPlanRepository,
)
from app.adapters.storage.postgres.subscription.repositories import (
    SubscriptionRepository,
)
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.feature_flags import is_feature_enabled
from app.domain.entities.lead import Lead, LeadSource, LeadStatus
from app.domain.entities.lead_activity import LeadActivity, LeadActivityType
from app.domain.entities.member import MemberStatus
from app.domain.entities.membership_plan import PlanType
from app.domain.entities.user import Role
from app.domain.exceptions import (
    FeatureDisabledError,
    InsufficientPermissionsError,
    InvalidLeadStatusTransitionError,
    InvalidSubscriptionStateTransitionError,
    LeadAlreadyConvertedError,
    LeadNotFoundError,
    MemberAlreadyExistsError,
    MembershipPlanNotFoundError,
    SubscriptionPlanMismatchError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import TokenPayload
    from app.domain.entities.member import Member
    from app.domain.entities.subscription import PaymentMethod, Subscription


logger = logging.getLogger(__name__)


# ── DTOs ──────────────────────────────────────────────────────────────


@dataclass
class ConvertResult:
    """Return shape of ``LeadService.convert`` — the three rows the
    transaction wrote."""

    lead: Lead
    member: Member
    subscription: Subscription


@dataclass
class LeadStats:
    """Backs the dashboard widget + Kanban column counts."""

    counts: dict[LeadStatus, int]
    conversion_rate_30d: float | None  # None if no leads created in window


# ── Service ───────────────────────────────────────────────────────────


class LeadService:
    """Pipeline CRUD + activities + convert."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LeadRepository(session)
        self._activity_repo = LeadActivityRepository(session)
        self._tenant_repo = TenantRepository(session)
        self._user_repo = UserRepository(session)
        self._member_repo = MemberRepository(session)
        self._plan_repo = MembershipPlanRepository(session)
        self._sub_repo = SubscriptionRepository(session)
        # The convert flow uses repos directly (member + sub) rather
        # than calling MemberService / SubscriptionService:
        #   - MemberService.create commits per call → would break
        #     atomicity here.
        #   - SubscriptionService gates on staff+ which excludes sales,
        #     and sales is the primary user of convert.
        # Inlining keeps both other services untouched and the convert
        # flow self-contained as a single transaction. Tenant scoping +
        # role gates are enforced above by ``_require_leads_enabled`` /
        # ``_require_writer``.

    # ── Lead CRUD ───────────────────────────────────────────────────

    async def create(
        self,
        *,
        caller: TokenPayload,
        first_name: str,
        last_name: str,
        phone: str,
        email: str | None = None,
        source: LeadSource = LeadSource.OTHER,
        assigned_to: _UUID | None = None,
        notes: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Lead:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)

        if assigned_to is not None:
            await self._assert_user_in_tenant(assigned_to, tenant_id)

        lead = await self._repo.create(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            source=source,
            assigned_to=assigned_to,
            notes=notes,
            custom_fields=custom_fields,
        )
        await self._session.commit()
        logger.info(
            "lead.created",
            extra={
                "event": "lead.created",
                "tenant_id": str(tenant_id),
                "lead_id": str(lead.id),
                "source": source.value,
                "assigned_to": str(assigned_to) if assigned_to else None,
            },
        )
        return lead

    async def get(self, *, caller: TokenPayload, lead_id: _UUID) -> Lead:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_any_role(caller)
        lead = await self._repo.find_by_id(lead_id)
        if lead is None or str(lead.tenant_id) != str(tenant_id):
            raise LeadNotFoundError(str(lead_id))
        return lead

    async def list_for_tenant(
        self,
        *,
        caller: TokenPayload,
        status: list[LeadStatus] | None = None,
        source: list[LeadSource] | None = None,
        assigned_to: _UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_any_role(caller)
        return await self._repo.list_for_tenant(
            tenant_id,
            status=status,
            source=source,
            assigned_to=assigned_to,
            search=search,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        **fields: Any,
    ) -> Lead:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)
        await self.get(caller=caller, lead_id=lead_id)

        # Status / lost_reason / converted_member_id flow through the
        # dedicated endpoints — strip from the generic update so a
        # crafty caller can't bypass the state machine via PATCH.
        for protected in (
            "status",
            "lost_reason",
            "converted_member_id",
            "tenant_id",
            "id",
            "created_at",
        ):
            fields.pop(protected, None)

        if "assigned_to" in fields and fields["assigned_to"] is not None:
            await self._assert_user_in_tenant(fields["assigned_to"], tenant_id)

        updated = await self._repo.update(lead_id, **fields)
        if updated is None:
            raise LeadNotFoundError(str(lead_id))
        await self._session.commit()
        return updated

    async def assign(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        user_id: _UUID | None,
    ) -> Lead:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)
        before = await self.get(caller=caller, lead_id=lead_id)

        if user_id is not None:
            await self._assert_user_in_tenant(user_id, tenant_id)

        updated = await self._repo.update(lead_id, assigned_to=user_id)
        if updated is None:
            raise LeadNotFoundError(str(lead_id))
        await self._session.commit()
        logger.info(
            "lead.assigned",
            extra={
                "event": "lead.assigned",
                "tenant_id": str(tenant_id),
                "lead_id": str(lead_id),
                "from": str(before.assigned_to) if before.assigned_to else None,
                "to": str(user_id) if user_id else None,
            },
        )
        return updated

    # ── Status transitions ──────────────────────────────────────────

    async def set_status(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        new_status: LeadStatus,
        lost_reason: str | None = None,
    ) -> Lead:
        """Move a lead through the pipeline (except into ``converted`` —
        use the convert endpoint for that). Emits a ``status_change``
        activity row in the same write.
        """
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)
        lead = await self.get(caller=caller, lead_id=lead_id)

        if new_status == LeadStatus.CONVERTED:
            # Drag-to-converted from the simple status path is rejected.
            # The convert endpoint is the only path (it requires a plan).
            raise InvalidLeadStatusTransitionError(
                str(lead_id), lead.status.value, new_status.value
            )

        if not lead.can_transition_to(new_status):
            raise InvalidLeadStatusTransitionError(
                str(lead_id), lead.status.value, new_status.value
            )

        # Compose the update + activity payload based on the move.
        fields: dict[str, Any] = {"status": new_status}
        note_parts = [f"{lead.status.value} → {new_status.value}"]

        if new_status == LeadStatus.LOST:
            # Lost: persist the reason on the lead column AND in the
            # activity row (so reopen later still has the history).
            cleaned = (lost_reason or "").strip() or None
            fields["lost_reason"] = cleaned
            if cleaned:
                note_parts.append(f"reason: {cleaned}")
        else:
            # Any other transition (incl. reopen from lost) clears the
            # lost_reason column. The previous reason stays in its
            # historical activity row.
            fields["lost_reason"] = None

        updated = await self._repo.update(lead_id, **fields)
        if updated is None:
            raise LeadNotFoundError(str(lead_id))

        await self._activity_repo.create(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=LeadActivityType.STATUS_CHANGE,
            note="; ".join(note_parts),
            created_by=self._caller_uuid(caller),
        )
        await self._session.commit()
        logger.info(
            "lead.status_changed",
            extra={
                "event": "lead.status_changed",
                "tenant_id": str(tenant_id),
                "lead_id": str(lead_id),
                "from": lead.status.value,
                "to": new_status.value,
                "by": caller.sub,
                "lost_reason": fields.get("lost_reason"),
            },
        )
        return updated

    # ── Activities ──────────────────────────────────────────────────

    async def add_activity(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        type: LeadActivityType,
        note: str,
    ) -> LeadActivity:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)

        # status_change is system-only and blank notes are useless —
        # both reject as 422 via Pydantic at the schema layer. The
        # service trusts the route's validated input and only checks
        # the cross-resource state (lead exists, in tenant).
        await self.get(caller=caller, lead_id=lead_id)
        activity = await self._activity_repo.create(
            tenant_id=tenant_id,
            lead_id=lead_id,
            type=type,
            note=note.strip(),
            created_by=self._caller_uuid(caller),
        )
        await self._session.commit()
        logger.info(
            "lead.activity_added",
            extra={
                "event": "lead.activity_added",
                "tenant_id": str(tenant_id),
                "lead_id": str(lead_id),
                "activity_id": str(activity.id),
                "type": type.value,
            },
        )
        return activity

    async def list_activities(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LeadActivity]:
        await self._require_leads_enabled(caller)
        self._require_any_role(caller)
        await self.get(caller=caller, lead_id=lead_id)
        return await self._activity_repo.list_for_lead(
            lead_id, limit=limit, offset=offset
        )

    # ── Lost reasons / stats ────────────────────────────────────────

    async def list_lost_reasons(
        self,
        *,
        caller: TokenPayload,
        days: int = 90,
        limit: int = 10,
    ) -> list[LostReasonRow]:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)
        since = datetime.now(UTC) - timedelta(days=max(1, days))
        return await self._repo.top_lost_reasons(tenant_id, since=since, limit=limit)

    async def stats(self, *, caller: TokenPayload) -> LeadStats:
        tenant_id = await self._require_leads_enabled(caller)
        self._require_any_role(caller)
        raw = await self._repo.count_by_status(tenant_id)
        # Ensure every status is represented (zero-fill for the Kanban).
        counts: dict[LeadStatus, int] = {s: raw.get(s, 0) for s in LeadStatus}

        since = datetime.now(UTC) - timedelta(days=30)
        denom = await self._repo.count_created_since(tenant_id, since=since)
        if denom == 0:
            rate: float | None = None
        else:
            num = await self._repo.count_converted_since(tenant_id, since=since)
            rate = num / denom

        return LeadStats(counts=counts, conversion_rate_30d=rate)

    # ── Convert (atomic txn) ────────────────────────────────────────

    async def convert(
        self,
        *,
        caller: TokenPayload,
        lead_id: _UUID,
        plan_id: _UUID,
        payment_method: PaymentMethod,
        start_date: date | None = None,
        copy_notes_to_member: bool = True,
    ) -> ConvertResult:
        """Atomic: lead → Member + first Subscription, all in one txn.

        Steps (single Postgres transaction):

        1. Re-read the lead, reject if already converted.
        2. Phone-collision pre-check against ``members`` for a clean
           409. The DB partial UNIQUE catches it too as a fallback.
        3. Create the member via ``MemberService.create(commit=False)``
           — auto-fills name/phone/email/notes from the lead.
        4. Create the first subscription via
           ``SubscriptionService.create(commit=False)`` — uses the same
           plan validation, price snapshot, and member-status sync as
           any other enrollment.
        5. Update the lead: status='converted', converted_member_id =
           new member id, lost_reason=None.
        6. Append a ``status_change`` activity row.
        7. Single commit at the end.

        On any failure the entire transaction rolls back. Caller can
        re-attempt after fixing the underlying issue (e.g. resolving
        the phone collision by linking to the existing member instead).
        """
        tenant_id = await self._require_leads_enabled(caller)
        self._require_writer(caller)

        lead = await self.get(caller=caller, lead_id=lead_id)
        if lead.status == LeadStatus.CONVERTED:
            raise LeadAlreadyConvertedError(str(lead_id))

        # Phone collision pre-check — surface a typed 409 rather than
        # depending on the DB partial UNIQUE alone.
        existing = await self._member_repo.find_by_tenant_and_phone(tenant_id, lead.phone)
        if existing is not None:
            raise MemberAlreadyExistsError(lead.phone)

        member_notes = lead.notes if copy_notes_to_member else None

        # Plan validation up-front so the rollback path is cheap.
        # Inlined rather than reusing SubscriptionService.create because
        # that service gates on staff+ which excludes sales — and sales
        # is the primary user of the convert flow. The business rules
        # below mirror SubscriptionService.create exactly.
        plan = await self._plan_repo.find_by_id(plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(str(plan_id))
        if str(plan.tenant_id) != str(tenant_id):
            raise SubscriptionPlanMismatchError()
        if not plan.is_active:
            raise InvalidSubscriptionStateTransitionError(
                current="inactive", action="subscribe to"
            )

        try:
            # 1. Member — direct repo write (no commit). Auto-fills the
            #    name/phone/email from the lead. Mirrors what
            #    MemberService.create does, minus the commit.
            member = await self._member_repo.create(
                tenant_id=tenant_id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                phone=lead.phone,
                email=lead.email,
                notes=member_notes,
                join_date=start_date,
            )

            # 2. Subscription — direct repo call so we don't hit the
            #    SubscriptionService staff+ gate. Same business logic:
            #    snapshot price + currency from the plan, resolve
            #    expires_at from plan type / duration, ACTIVE status.
            resolved_start = start_date or date.today()
            resolved_expires = self._resolve_expires_at(
                plan=plan, started_at=resolved_start
            )
            subscription = await self._sub_repo.create(
                tenant_id=tenant_id,
                member_id=member.id,
                plan_id=plan_id,
                price_cents=plan.price_cents,
                currency=plan.currency,
                started_at=resolved_start,
                expires_at=resolved_expires,
                payment_method=payment_method,
                created_by=self._caller_uuid(caller),
                event_data={"plan_id": str(plan_id), "lead_id": str(lead_id)},
            )
            # Sync member.status to ACTIVE (matches SubscriptionService —
            # the member was just created with active default but doing
            # this defensively keeps the convert flow's invariants
            # identical to a direct enrollment).
            await self._member_repo.update(member.id, status=MemberStatus.ACTIVE)

            # 3. Flip the lead.
            updated_lead = await self._repo.update(
                lead_id,
                status=LeadStatus.CONVERTED,
                converted_member_id=member.id,
                lost_reason=None,
            )
            if updated_lead is None:
                # Defensive — find_by_id between get() and update() is
                # extraordinarily unlikely to vanish, but if it does we
                # want a clean rollback.
                raise LeadNotFoundError(str(lead_id))

            # 4. Status_change activity row.
            await self._activity_repo.create(
                tenant_id=tenant_id,
                lead_id=lead_id,
                type=LeadActivityType.STATUS_CHANGE,
                note=(
                    f"{lead.status.value} → converted; "
                    f"member={member.id}; plan={plan_id}"
                ),
                created_by=self._caller_uuid(caller),
            )

            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            logger.info(
                "lead.convert_failed",
                extra={
                    "event": "lead.convert_failed",
                    "tenant_id": str(tenant_id),
                    "lead_id": str(lead_id),
                    "error_code": getattr(exc, "code", "UNKNOWN"),
                },
            )
            raise

        logger.info(
            "lead.converted",
            extra={
                "event": "lead.converted",
                "tenant_id": str(tenant_id),
                "lead_id": str(lead_id),
                "member_id": str(member.id),
                "subscription_id": str(subscription.id),
                "plan_id": str(plan_id),
            },
        )
        return ConvertResult(
            lead=updated_lead, member=member, subscription=subscription
        )

    # ── Cross-resource helpers ──────────────────────────────────────

    @staticmethod
    def _resolve_expires_at(*, plan, started_at: date) -> date | None:
        """Mirror of ``SubscriptionService._resolve_expires_at`` for the
        convert flow's auto-resolved start dates.

        - one-time plan with duration_days → started_at + duration_days
        - recurring → None (card-auto runs until cancelled)

        Convert doesn't expose an ``expires_at`` override because the
        UX is "owner picks a plan" — the plan defines the duration.
        """
        if plan.type == PlanType.ONE_TIME and plan.duration_days is not None:
            return started_at + timedelta(days=plan.duration_days)
        return None

    async def _assert_user_in_tenant(self, user_id: _UUID, tenant_id: _UUID) -> None:
        user = await self._user_repo.find_by_id(user_id)
        if user is None or str(user.tenant_id) != str(tenant_id):
            # 404 — don't leak the existence of cross-tenant users.
            raise UserNotFoundError(str(user_id))

    # ── Role + feature gates ────────────────────────────────────────

    async def _require_leads_enabled(self, caller: TokenPayload) -> _UUID:
        """Assert caller has a tenant and Leads is ON for that tenant.
        Returns the tenant UUID for convenience."""
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        tenant_id = _UUID(caller.tenant_id)
        tenant = await self._tenant_repo.find_by_id(tenant_id)
        if tenant is None:
            raise InsufficientPermissionsError()
        if not is_feature_enabled(tenant, "leads"):
            raise FeatureDisabledError("leads")
        return tenant_id

    @staticmethod
    def _require_writer(caller: TokenPayload) -> None:
        """Owner / sales / super_admin can mutate leads. Staff is read-only.
        Coach has no access at all (RequireFeature already blocks; this is
        defense in depth)."""
        if caller.role not in (
            Role.OWNER.value,
            Role.SALES.value,
            Role.SUPER_ADMIN.value,
        ):
            raise InsufficientPermissionsError()

    @staticmethod
    def _require_any_role(caller: TokenPayload) -> None:
        """Reads — owner / sales / super_admin / staff. Coach blocked."""
        if caller.role == Role.COACH.value:
            raise InsufficientPermissionsError()

    @staticmethod
    def _caller_uuid(caller: TokenPayload) -> _UUID | None:
        if caller.sub is None:
            return None
        try:
            return _UUID(caller.sub)
        except (TypeError, ValueError):
            return None


__all__ = ["LeadService", "ConvertResult", "LeadStats"]
