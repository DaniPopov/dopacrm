"""E2E tests for member CRUD endpoints + security + tenant scoping."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
def gym_setup() -> dict:
    """Seed a tenant + an owner user in that tenant. Returns ids + token."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        # Fetch default saas plan (seeded by migration 0003)
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()

        # Create tenant
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:slug, :name, :plan, 'active') RETURNING id"
            ),
            {"slug": f"gym-{uuid4().hex[:8]}", "name": "Test Gym", "plan": plan_id},
        ).scalar_one()

        # Create owner user in that tenant
        owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:email, :pwd, 'owner', :tid, true) RETURNING id"
            ),
            {
                "email": f"owner-{uuid4().hex[:6]}@gym.com",
                "pwd": hash_password("OwnerPass1!"),
                "tid": tenant_id,
            },
        ).scalar_one()

        # Create staff user in same tenant
        staff_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:email, :pwd, 'staff', :tid, true) RETURNING id"
            ),
            {
                "email": f"staff-{uuid4().hex[:6]}@gym.com",
                "pwd": hash_password("StaffPass1!"),
                "tid": tenant_id,
            },
        ).scalar_one()
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_id": str(owner_id),
        "staff_id": str(staff_id),
        "owner_token": create_access_token(
            user_id=str(owner_id), role="owner", tenant_id=str(tenant_id), secret_key=secret
        ),
        "staff_token": create_access_token(
            user_id=str(staff_id), role="staff", tenant_id=str(tenant_id), secret_key=secret
        ),
    }


@pytest.fixture
def owner_headers(gym_setup: dict) -> dict:
    return {"Authorization": f"Bearer {gym_setup['owner_token']}"}


@pytest.fixture
def staff_headers(gym_setup: dict) -> dict:
    return {"Authorization": f"Bearer {gym_setup['staff_token']}"}


def _create_member(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "first_name": "Dana",
        "last_name": "Cohen",
        "phone": f"+972-50-{uuid4().hex[:7]}",
        **overrides,
    }
    resp = client.post("/api/v1/members", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_member(client: TestClient, owner_headers: dict, gym_setup: dict) -> None:
    data = _create_member(
        client,
        owner_headers,
        first_name="Dana",
        last_name="Cohen",
        email="dana@example.com",
        gender="female",
        custom_fields={"referral_source": "walk_in"},
    )
    assert data["first_name"] == "Dana"
    assert data["last_name"] == "Cohen"
    assert data["email"] == "dana@example.com"
    assert data["gender"] == "female"
    assert data["status"] == "active"
    assert data["tenant_id"] == gym_setup["tenant_id"]
    assert data["custom_fields"] == {"referral_source": "walk_in"}


def test_create_member_by_staff(client: TestClient, staff_headers: dict) -> None:
    data = _create_member(client, staff_headers)
    assert data["status"] == "active"


def test_create_member_duplicate_phone_in_tenant_returns_409(
    client: TestClient, owner_headers: dict
) -> None:
    _create_member(client, owner_headers, phone="+972-50-SAME")
    resp = client.post(
        "/api/v1/members",
        headers=owner_headers,
        json={"first_name": "Other", "last_name": "Person", "phone": "+972-50-SAME"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "MEMBER_ALREADY_EXISTS"


# ── Read ──────────────────────────────────────────────────────────────────────


def test_list_members_scoped_to_tenant(client: TestClient, owner_headers: dict) -> None:
    _create_member(client, owner_headers, first_name="A")
    _create_member(client, owner_headers, first_name="B")
    resp = client.get("/api/v1/members", headers=owner_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_list_members_filter_by_status(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    client.post(f"/api/v1/members/{m['id']}/freeze", headers=owner_headers)
    resp = client.get("/api/v1/members?status=frozen", headers=owner_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["status"] == "frozen"


def test_list_members_search(client: TestClient, owner_headers: dict) -> None:
    _create_member(client, owner_headers, first_name="Dana", last_name="Cohen")
    _create_member(client, owner_headers, first_name="Yossi", last_name="Levi")
    resp = client.get("/api/v1/members?search=cohen", headers=owner_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["last_name"] == "Cohen"


def test_get_member_by_id(client: TestClient, owner_headers: dict) -> None:
    created = _create_member(client, owner_headers)
    resp = client.get(f"/api/v1/members/{created['id']}", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_member_not_found(client: TestClient, owner_headers: dict) -> None:
    resp = client.get(f"/api/v1/members/{uuid4()}", headers=owner_headers)
    assert resp.status_code == 404


# ── Tenant scoping ────────────────────────────────────────────────────────────


def test_member_from_other_tenant_is_404(
    client: TestClient, owner_headers: dict, gym_setup: dict
) -> None:
    """A member in tenant A cannot be seen from tenant B's owner token."""
    # Create member under tenant A
    m_a = _create_member(client, owner_headers)

    # Build a second tenant + owner
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_b_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:slug, 'B', :plan, 'active') RETURNING id"
            ),
            {"slug": f"b-{uuid4().hex[:8]}", "plan": plan_id},
        ).scalar_one()
        owner_b_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:email, :pwd, 'owner', :tid, true) RETURNING id"
            ),
            {
                "email": f"b-{uuid4().hex[:6]}@gym.com",
                "pwd": hash_password("Pass1234!"),
                "tid": tenant_b_id,
            },
        ).scalar_one()
        session.commit()
    engine.dispose()

    token_b = create_access_token(
        user_id=str(owner_b_id),
        role="owner",
        tenant_id=str(tenant_b_id),
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get(f"/api/v1/members/{m_a['id']}", headers=headers_b)
    # Returns 404 (not 403) to avoid leaking existence
    assert resp.status_code == 404


# ── State transitions ────────────────────────────────────────────────────────


def test_freeze_then_unfreeze(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    r = client.post(f"/api/v1/members/{m['id']}/freeze", headers=owner_headers, json={})
    assert r.status_code == 200
    assert r.json()["status"] == "frozen"
    assert r.json()["frozen_at"] is not None

    r = client.post(f"/api/v1/members/{m['id']}/unfreeze", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["frozen_at"] is None


def test_freeze_already_frozen_returns_409(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    client.post(f"/api/v1/members/{m['id']}/freeze", headers=owner_headers, json={})
    r = client.post(f"/api/v1/members/{m['id']}/freeze", headers=owner_headers, json={})
    assert r.status_code == 409
    assert r.json()["error"] == "MEMBER_INVALID_TRANSITION"


def test_unfreeze_active_member_returns_409(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    r = client.post(f"/api/v1/members/{m['id']}/unfreeze", headers=owner_headers)
    assert r.status_code == 409


def test_cancel_owner_only(client: TestClient, owner_headers: dict, staff_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    # staff is blocked
    r = client.post(f"/api/v1/members/{m['id']}/cancel", headers=staff_headers)
    assert r.status_code == 403
    # owner succeeds
    r = client.post(f"/api/v1/members/{m['id']}/cancel", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancelled_at"] is not None


def test_cancel_already_cancelled_returns_409(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    client.post(f"/api/v1/members/{m['id']}/cancel", headers=owner_headers)
    r = client.post(f"/api/v1/members/{m['id']}/cancel", headers=owner_headers)
    assert r.status_code == 409


# ── Update ────────────────────────────────────────────────────────────────────


def test_update_member(client: TestClient, owner_headers: dict) -> None:
    m = _create_member(client, owner_headers)
    r = client.patch(
        f"/api/v1/members/{m['id']}",
        headers=owner_headers,
        json={"notes": "Moved to morning sessions"},
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "Moved to morning sessions"


# ── super_admin cannot create members ────────────────────────────────────────


def test_super_admin_cannot_create_member(client: TestClient, auth_headers: dict) -> None:
    """super_admin is platform-level, not gym-level. Member ops reject them."""
    resp = client.post(
        "/api/v1/members",
        headers=auth_headers,
        json={"first_name": "X", "last_name": "Y", "phone": "+972-50-no"},
    )
    assert resp.status_code == 403
