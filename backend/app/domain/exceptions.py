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
