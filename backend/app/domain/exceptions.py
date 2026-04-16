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
