"""All custom application exceptions.

Lives in ``domain/`` because:
1. Adapters can raise them (``adapter → domain`` is allowed by hexagonal rules)
2. Multiple services may raise the same exception — single source of truth
3. The API layer's ``error_handler.py`` maps ``AppError.code → HTTPException``
   in one place

Every exception inherits from ``AppError`` and carries a string ``code``
field. Services and adapters raise these — they NEVER raise
``HTTPException`` directly.
"""


class AppError(Exception):
    """Base for every application error.

    Args:
        message: Human-readable description.
        code: Stable string identifier (UPPER_SNAKE) used by the API layer
            to map to an HTTP status code and by clients to handle errors
            programmatically. Never change a code without versioning.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ── Auth ─────────────────────────────────────────────────────────────────────
class InvalidCredentialsError(AppError):
    """Wrong email/password combination."""

    def __init__(self) -> None:
        super().__init__("Invalid email or password", "INVALID_CREDENTIALS")


class InsufficientPermissionsError(AppError):
    """Authenticated user lacks the required role."""

    def __init__(self) -> None:
        super().__init__("Insufficient permissions", "INSUFFICIENT_PERMISSIONS")


# ── User ─────────────────────────────────────────────────────────────────────
class UserNotFoundError(AppError):
    """No user matches the given identifier (id or email)."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"User not found: {identifier}", "USER_NOT_FOUND")


class UserAlreadyExistsError(AppError):
    """A user with this email already exists in the target scope."""

    def __init__(self, email: str) -> None:
        super().__init__(f"User already exists: {email}", "USER_ALREADY_EXISTS")


# ── Tenant ───────────────────────────────────────────────────────────────────
class TenantNotFoundError(AppError):
    """No tenant matches the given id or slug."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Tenant not found: {identifier}", "TENANT_NOT_FOUND")


class TenantSuspendedError(AppError):
    """The tenant's status is inactive — block all tenant traffic."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant suspended: {tenant_id}", "TENANT_SUSPENDED")


# ── Membership Plan ──────────────────────────────────────────────────────────
class MembershipPlanNotFoundError(AppError):
    """No plan matches the given id in the caller's tenant."""

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan not found: {plan_id}", "PLAN_NOT_FOUND")


class MembershipPlanAlreadyExistsError(AppError):
    """A plan with this name already exists in this tenant."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Plan with this name already exists in this tenant: {name}",
            "PLAN_ALREADY_EXISTS",
        )


class InvalidPlanShapeError(AppError):
    """Plan fields don't satisfy the shape rules.

    Examples: one_time plan without duration_days, entitlement with
    reset='unlimited' but quantity provided, class_id that belongs to
    a different tenant.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid plan shape: {reason}", "PLAN_INVALID_SHAPE")


# ── Class ────────────────────────────────────────────────────────────────────
class GymClassNotFoundError(AppError):
    """No class type matches the given id in the caller's tenant."""

    def __init__(self, class_id: str) -> None:
        super().__init__(f"Class not found: {class_id}", "CLASS_NOT_FOUND")


class GymClassAlreadyExistsError(AppError):
    """A class with this name already exists in this tenant."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Class with this name already exists in this tenant: {name}",
            "CLASS_ALREADY_EXISTS",
        )


# ── Member ───────────────────────────────────────────────────────────────────
class MemberNotFoundError(AppError):
    """No member matches the given id in the caller's tenant."""

    def __init__(self, member_id: str) -> None:
        super().__init__(f"Member not found: {member_id}", "MEMBER_NOT_FOUND")


class MemberAlreadyExistsError(AppError):
    """Phone number already in use for another member in this tenant."""

    def __init__(self, phone: str) -> None:
        super().__init__(
            f"Member with phone already exists in this tenant: {phone}",
            "MEMBER_ALREADY_EXISTS",
        )


class InvalidMemberStatusTransitionError(AppError):
    """Attempted a status change the state machine doesn't allow.

    Examples: unfreezing an active member, freezing a cancelled member.
    """

    def __init__(self, current: str, action: str) -> None:
        super().__init__(
            f"Cannot {action} member in status '{current}'",
            "MEMBER_INVALID_TRANSITION",
        )


# ── Subscription ─────────────────────────────────────────────────────────────
class SubscriptionNotFoundError(AppError):
    """No subscription matches the given id in the caller's tenant."""

    def __init__(self, sub_id: str) -> None:
        super().__init__(f"Subscription not found: {sub_id}", "SUBSCRIPTION_NOT_FOUND")


class InvalidSubscriptionStateTransitionError(AppError):
    """Attempted a transition the state machine doesn't allow.

    Examples: freezing a cancelled sub, renewing a cancelled sub,
    changing the plan of an expired sub (must renew or create new).
    """

    def __init__(self, current: str, action: str) -> None:
        super().__init__(
            f"Cannot {action} subscription in status '{current}'",
            "SUBSCRIPTION_INVALID_TRANSITION",
        )


class MemberAlreadyHasActiveSubscriptionError(AppError):
    """Enrolling a member who already has a live (active/frozen) sub.

    Enforced in the service for a clean 409; the DB partial UNIQUE
    index is the last line of defense.
    """

    def __init__(self, member_id: str) -> None:
        super().__init__(
            f"Member already has a live subscription: {member_id}",
            "MEMBER_HAS_ACTIVE_SUBSCRIPTION",
        )


class SamePlanChangeError(AppError):
    """change-plan was called with the same plan as the current subscription.

    Prevents ghost ``replaced`` rows that point at an identical plan —
    those would pollute churn/upgrade reports with no-op transitions.
    """

    def __init__(self) -> None:
        super().__init__(
            "New plan must differ from the current plan",
            "SUBSCRIPTION_SAME_PLAN",
        )


class SubscriptionPlanMismatchError(AppError):
    """Plan and member belong to different tenants. Belt-and-suspenders
    vs the FK — surfaces as 422 with a useful code."""

    def __init__(self) -> None:
        super().__init__(
            "Plan and member belong to different tenants",
            "SUBSCRIPTION_PLAN_TENANT_MISMATCH",
        )


# ── Attendance / class entries ───────────────────────────────────────────────
class ClassEntryNotFoundError(AppError):
    """No class entry matches the given id in the caller's tenant."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"Class entry not found: {entry_id}", "CLASS_ENTRY_NOT_FOUND")


class MemberHasNoActiveSubscriptionError(AppError):
    """Can't check in a member who has no live subscription.

    Returned as 409 — the UI shows "no active subscription, enroll first"
    with a link to the subscription section on the member page.
    """

    def __init__(self, member_id: str) -> None:
        super().__init__(
            f"Member has no active subscription: {member_id}",
            "MEMBER_NO_ACTIVE_SUBSCRIPTION",
        )


class QuotaExceededError(AppError):
    """Entitlement exists but the reset-period quota is full.

    The service raises this if the caller didn't pass ``override=true``.
    The UI catches the 409 + kind=quota_exceeded and shows the override
    modal; if staff confirms, the request is replayed with override=true.
    """

    def __init__(self, used: int, quantity: int) -> None:
        super().__init__(
            f"Quota exceeded: {used}/{quantity} used in the current window",
            "ATTENDANCE_QUOTA_EXCEEDED",
        )


class ClassNotCoveredByPlanError(AppError):
    """Member's plan has no entitlement for this class (neither exact-class
    nor any-class wildcard).

    Same pattern as QuotaExceededError — UI shows override modal.
    """

    def __init__(self, class_id: str) -> None:
        super().__init__(
            f"Class not covered by the member's plan: {class_id}",
            "ATTENDANCE_CLASS_NOT_COVERED",
        )


class UndoWindowExpiredError(AppError):
    """The 24h undo window has closed. Entry stays as-is.

    Corrections past the window are future work (audit log / owner
    approval). v1 just refuses.
    """

    def __init__(self, hours_since_entry: float) -> None:
        super().__init__(
            f"Undo window expired ({hours_since_entry:.1f}h since entry)",
            "ATTENDANCE_UNDO_WINDOW_EXPIRED",
        )


class ClassEntryAlreadyUndoneError(AppError):
    """Double-undo guard — entry was already soft-deleted."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(
            f"Class entry already undone: {entry_id}",
            "ATTENDANCE_ALREADY_UNDONE",
        )


# ── Coaches ──────────────────────────────────────────────────────────────────
class CoachNotFoundError(AppError):
    """No coach matches the given id (or exists in another tenant)."""

    def __init__(self, coach_id: str) -> None:
        super().__init__(f"Coach not found: {coach_id}", "COACH_NOT_FOUND")


class CoachAlreadyLinkedToUserError(AppError):
    """invite-user called on a coach that already has ``user_id`` set."""

    def __init__(self, coach_id: str) -> None:
        super().__init__(
            f"Coach already linked to a user: {coach_id}",
            "COACH_ALREADY_LINKED",
        )


class CoachStatusTransitionError(AppError):
    """Illegal state transition on a coach (e.g. freeze a cancelled one)."""

    def __init__(self, coach_id: str, current: str, attempted: str) -> None:
        super().__init__(
            f"Cannot {attempted} coach {coach_id} in status {current}",
            "COACH_STATUS_TRANSITION",
        )


class ClassCoachLinkNotFoundError(AppError):
    """No (class, coach) link row matches."""

    def __init__(self, link_id: str) -> None:
        super().__init__(
            f"Class-coach link not found: {link_id}",
            "CLASS_COACH_LINK_NOT_FOUND",
        )


class ClassCoachConflictError(AppError):
    """A duplicate (class, coach, role) link — enforced by ``ux_class_coaches_role``.

    Also raised when the service detects two primaries on overlapping
    weekdays (the unique index can't express the "array overlap" rule,
    so the service does the check).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail, "CLASS_COACH_CONFLICT")


class InvalidPayModelError(AppError):
    """``pay_model`` outside the allowed enum values."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"Invalid pay_model: {value!r}. Expected one of "
            "'fixed', 'per_session', 'per_attendance'.",
            "COACH_INVALID_PAY_MODEL",
        )


class InvalidEarningsRangeError(AppError):
    """``from`` > ``to`` in an earnings query, or range outside a reasonable
    bound (e.g. negative window)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, "COACH_INVALID_EARNINGS_RANGE")


# ── Feature flags ─────────────────────────────────────────────────────────────
class FeatureDisabledError(AppError):
    """The requested feature is not enabled for this tenant.

    Maps to HTTP 403 — the feature *exists*, the caller is authenticated,
    but tenant config denies access. Distinct from
    ``InsufficientPermissionsError`` (role-level denial) and from 404
    (tenant-scope mismatch).
    """

    def __init__(self, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is not enabled for this tenant",
            "FEATURE_DISABLED",
        )
        self.feature = feature


# ── Schedule ─────────────────────────────────────────────────────────────────
class ClassScheduleTemplateNotFoundError(AppError):
    """No template matches the id (or it's in another tenant)."""

    def __init__(self, template_id: str) -> None:
        super().__init__(
            f"Schedule template not found: {template_id}",
            "SCHEDULE_TEMPLATE_NOT_FOUND",
        )


class ClassSessionNotFoundError(AppError):
    """No session matches the id (or it's in another tenant)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Class session not found: {session_id}",
            "SCHEDULE_SESSION_NOT_FOUND",
        )


class SessionStatusTransitionError(AppError):
    """Illegal state transition on a session (e.g. cancel an already-cancelled session)."""

    def __init__(self, session_id: str, current: str, attempted: str) -> None:
        super().__init__(
            f"Cannot {attempted} session {session_id} in status {current}",
            "SCHEDULE_SESSION_TRANSITION",
        )


class InvalidBulkRangeError(AppError):
    """Bulk action range invalid (from > to, or range spans > 1 year)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, "SCHEDULE_INVALID_BULK_RANGE")


# ── Leads ────────────────────────────────────────────────────────────────────
class LeadNotFoundError(AppError):
    """No lead matches the given id (or it's in another tenant)."""

    def __init__(self, lead_id: str) -> None:
        super().__init__(f"Lead not found: {lead_id}", "LEAD_NOT_FOUND")


class InvalidLeadStatusTransitionError(AppError):
    """Attempted a pipeline transition the state machine doesn't allow.

    Examples: setting status back to ``new`` from ``contacted``, or
    sending ``new_status='converted'`` to the simple status endpoint
    (the convert endpoint is the only path to ``converted``).
    """

    def __init__(self, lead_id: str, current: str, attempted: str) -> None:
        super().__init__(
            f"Cannot transition lead {lead_id} from {current} to {attempted}",
            "INVALID_LEAD_STATUS_TRANSITION",
        )


class LeadAlreadyConvertedError(AppError):
    """Convert called on a lead that's already in the ``converted`` state.

    Distinct from the transition error — this is a re-convert attempt on
    a terminal state, surfaced with its own code so the UI can show a
    "this lead was already converted" message with a link to the member.
    """

    def __init__(self, lead_id: str) -> None:
        super().__init__(
            f"Lead already converted: {lead_id}",
            "LEAD_ALREADY_CONVERTED",
        )


# ── Payments ─────────────────────────────────────────────────────────────────
class PaymentNotFoundError(AppError):
    """No payment matches the given id (or it's in another tenant)."""

    def __init__(self, payment_id: str) -> None:
        super().__init__(f"Payment not found: {payment_id}", "PAYMENT_NOT_FOUND")


class PaymentAmountInvalidError(AppError):
    """Amount fails the shape rules (zero, or future-dated, or sign mismatch).

    The DB CHECK enforces non-zero too, but the service catches the case
    earlier with a typed code so the UI can show "סכום חייב להיות חיובי"
    instead of a generic 422.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid payment amount: {reason}", "PAYMENT_AMOUNT_INVALID")


class PaymentRefundExceedsOriginalError(AppError):
    """Refund attempt would push cumulative refunds past the original amount.

    Returned as 409 — the request is structurally valid but the math
    rejects it. The UI shows "סכום ההחזר גדול מהיתרה הניתנת להחזר"
    and re-fetches the remaining-refundable display.
    """

    def __init__(self, payment_id: str, requested: int, remaining: int) -> None:
        super().__init__(
            f"Refund of {requested} exceeds remaining {remaining} on payment {payment_id}",
            "PAYMENT_REFUND_EXCEEDS_ORIGINAL",
        )


class PaymentAlreadyFullyRefundedError(AppError):
    """Distinct from "exceeds" — the original is already at zero remaining.

    Surfaced with its own code so the UI can hide the refund button
    rather than show an error message.
    """

    def __init__(self, payment_id: str) -> None:
        super().__init__(
            f"Payment already fully refunded: {payment_id}",
            "PAYMENT_ALREADY_FULLY_REFUNDED",
        )
