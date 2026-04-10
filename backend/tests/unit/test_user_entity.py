"""Unit tests for the User domain entity's pure logic methods."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.user import Role, User


def _make_user(
    *,
    role: Role,
    tenant_id=None,
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="user@example.com",
        role=role,
        is_active=True,
        oauth_provider=None,
        created_at=now,
        updated_at=now,
    )


def test_super_admin_is_super_admin() -> None:
    user = _make_user(role=Role.SUPER_ADMIN)
    assert user.is_super_admin() is True


def test_owner_is_not_super_admin() -> None:
    user = _make_user(role=Role.OWNER, tenant_id=uuid4())
    assert user.is_super_admin() is False


def test_super_admin_can_manage_any_tenant() -> None:
    user = _make_user(role=Role.SUPER_ADMIN)
    assert user.can_manage_tenant(uuid4()) is True
    assert user.can_manage_tenant(uuid4()) is True


def test_owner_can_manage_only_own_tenant() -> None:
    tenant_id = uuid4()
    user = _make_user(role=Role.OWNER, tenant_id=tenant_id)
    assert user.can_manage_tenant(tenant_id) is True
    assert user.can_manage_tenant(uuid4()) is False


def test_staff_can_manage_only_own_tenant() -> None:
    tenant_id = uuid4()
    user = _make_user(role=Role.STAFF, tenant_id=tenant_id)
    assert user.can_manage_tenant(tenant_id) is True
    assert user.can_manage_tenant(uuid4()) is False


def test_sales_cannot_manage_anything() -> None:
    tenant_id = uuid4()
    user = _make_user(role=Role.SALES, tenant_id=tenant_id)
    assert user.can_manage_tenant(tenant_id) is False
    assert user.can_manage_tenant(uuid4()) is False


def test_owner_cannot_access_other_tenant() -> None:
    """An owner from tenant A must NOT be able to manage tenant B."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    owner_a = _make_user(role=Role.OWNER, tenant_id=tenant_a)
    assert owner_a.can_manage_tenant(tenant_a) is True
    assert owner_a.can_manage_tenant(tenant_b) is False
