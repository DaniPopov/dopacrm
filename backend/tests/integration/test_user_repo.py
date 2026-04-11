"""Integration tests for UserRepository — real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.security import hash_password
from app.domain.entities.user import Role, User
from app.domain.exceptions import UserAlreadyExistsError


@pytest.fixture
def repo(session) -> UserRepository:
    return UserRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None, "default saas plan must be seeded for tests"
    return plan.id


async def _create_tenant(tenant_repo: TenantRepository, plan_id) -> ...:
    """Helper: create a tenant and return it (for FK references)."""
    return await tenant_repo.create(
        slug=f"test-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


# ── Create ────────────────────────────────────────────────────────────────────


async def test_create_user_returns_domain_entity(repo: UserRepository) -> None:
    user = await repo.create(
        email="test@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password("test123456"),
    )
    assert isinstance(user, User)
    assert user.email == "test@example.com"
    assert user.role == Role.SUPER_ADMIN
    assert user.tenant_id is None
    assert user.is_active is True
    assert user.id is not None


async def test_create_user_with_tenant(
    repo: UserRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    user = await repo.create(
        email="owner@dopagym.com",
        role=Role.OWNER,
        tenant_id=tenant.id,
        password_hash=hash_password("secure123!"),
    )
    assert user.tenant_id == tenant.id
    assert user.role == Role.OWNER


async def test_create_duplicate_email_raises(repo: UserRepository) -> None:
    await repo.create(
        email="dupe@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password("pass12345"),
    )
    with pytest.raises(UserAlreadyExistsError):
        await repo.create(
            email="dupe@example.com",
            role=Role.SUPER_ADMIN,
            tenant_id=None,
            password_hash=hash_password("pass12345"),
        )


# ── Find ──────────────────────────────────────────────────────────────────────


async def test_find_by_id(repo: UserRepository) -> None:
    created = await repo.create(
        email="findme@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password("pass12345"),
    )
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.email == "findme@example.com"


async def test_find_by_id_not_found(repo: UserRepository) -> None:
    result = await repo.find_by_id(uuid4())
    assert result is None


async def test_find_by_email_super_admin(repo: UserRepository) -> None:
    await repo.create(
        email="super@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password("pass12345"),
    )
    found = await repo.find_by_email("super@example.com", tenant_id=None)
    assert found is not None
    assert found.email == "super@example.com"


async def test_find_by_email_not_found(repo: UserRepository) -> None:
    result = await repo.find_by_email("nonexistent@example.com", tenant_id=None)
    assert result is None


async def test_find_with_credentials(repo: UserRepository) -> None:
    pwd = "secret12345"
    await repo.create(
        email="creds@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password(pwd),
    )
    result = await repo.find_with_credentials("creds@example.com", tenant_id=None)
    assert result is not None
    user, pwd_hash = result
    assert user.email == "creds@example.com"
    assert pwd_hash is not None
    assert pwd_hash.startswith("$argon2")


# ── List ──────────────────────────────────────────────────────────────────────


async def test_list_all(repo: UserRepository) -> None:
    for i in range(3):
        await repo.create(
            email=f"user{i}@example.com",
            role=Role.SUPER_ADMIN,
            tenant_id=None,
            password_hash=hash_password("pass12345"),
        )
    users = await repo.list_all(limit=10, offset=0)
    assert len(users) >= 3


async def test_list_by_tenant(
    repo: UserRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant_a = await _create_tenant(tenant_repo, default_plan_id)
    tenant_b = await _create_tenant(tenant_repo, default_plan_id)
    await repo.create(
        email="a@gym.com",
        role=Role.OWNER,
        tenant_id=tenant_a.id,
        password_hash=hash_password("p12345678"),
    )
    await repo.create(
        email="b@gym.com",
        role=Role.OWNER,
        tenant_id=tenant_b.id,
        password_hash=hash_password("p12345678"),
    )

    users_a = await repo.list_by_tenant(tenant_a.id, limit=10, offset=0)
    assert len(users_a) == 1
    assert users_a[0].email == "a@gym.com"


# ── Update ────────────────────────────────────────────────────────────────────


async def test_update_user(
    repo: UserRepository,
    tenant_repo: TenantRepository,
    default_plan_id,
) -> None:
    tenant = await _create_tenant(tenant_repo, default_plan_id)
    user = await repo.create(
        email="update@example.com",
        role=Role.OWNER,
        tenant_id=tenant.id,
        password_hash=hash_password("pass12345"),
    )
    updated = await repo.update(user.id, role="staff")
    assert updated.role == Role.STAFF


async def test_soft_delete(repo: UserRepository) -> None:
    user = await repo.create(
        email="delete@example.com",
        role=Role.SUPER_ADMIN,
        tenant_id=None,
        password_hash=hash_password("pass12345"),
    )
    assert user.is_active is True
    updated = await repo.update(user.id, is_active=False)
    assert updated.is_active is False
