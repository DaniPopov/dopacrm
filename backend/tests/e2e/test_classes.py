"""E2E tests for class-catalog endpoints + security + tenant scoping."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
def gym_setup() -> dict:
    """Seed a tenant + owner + staff user. Returns ids + tokens."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:slug, :name, :plan, 'active') RETURNING id"
            ),
            {"slug": f"gym-{uuid4().hex[:8]}", "name": "Test Gym", "plan": plan_id},
        ).scalar_one()
        owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": f"o-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1!aa"), "t": tenant_id},
        ).scalar_one()
        staff_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'staff', :t, true) RETURNING id"
            ),
            {"e": f"s-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1!bb"), "t": tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
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


def _create_class(client: TestClient, headers: dict, **overrides) -> dict:
    body = {"name": "Spinning", **overrides}
    resp = client.post("/api/v1/classes", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_class_as_owner(client: TestClient, owner_headers: dict, gym_setup: dict) -> None:
    """Owner creates a class → 201, response shape correct, is_active=true."""
    data = _create_class(
        client,
        owner_headers,
        name="Yoga",
        description="Relaxing flow",
        color="#10B981",
    )
    assert data["name"] == "Yoga"
    assert data["description"] == "Relaxing flow"
    assert data["color"] == "#10B981"
    assert data["is_active"] is True
    assert data["tenant_id"] == gym_setup["tenant_id"]


def test_staff_cannot_create_class(client: TestClient, staff_headers: dict) -> None:
    """Staff → 403 on mutation. Catalog is owner-configured."""
    r = client.post("/api/v1/classes", headers=staff_headers, json={"name": "X"})
    assert r.status_code == 403


def test_super_admin_cannot_create_class(client: TestClient, auth_headers: dict) -> None:
    """super_admin is platform-level; class ops are gym-scoped → 403."""
    r = client.post("/api/v1/classes", headers=auth_headers, json={"name": "X"})
    assert r.status_code == 403


def test_create_duplicate_name_returns_409(client: TestClient, owner_headers: dict) -> None:
    """(tenant_id, name) UNIQUE → second insert → 409."""
    _create_class(client, owner_headers, name="Spinning")
    r = client.post("/api/v1/classes", headers=owner_headers, json={"name": "Spinning"})
    assert r.status_code == 409
    assert r.json()["error"] == "CLASS_ALREADY_EXISTS"


def test_create_name_required(client: TestClient, owner_headers: dict) -> None:
    """Missing name → 422 validation error."""
    r = client.post("/api/v1/classes", headers=owner_headers, json={})
    assert r.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────────────


def test_list_excludes_inactive_by_default(client: TestClient, owner_headers: dict) -> None:
    """Default listing hides deactivated classes — `include_inactive=true` shows them."""
    active = _create_class(client, owner_headers, name="Active")
    inactive = _create_class(client, owner_headers, name="Inactive")
    client.post(f"/api/v1/classes/{inactive['id']}/deactivate", headers=owner_headers)

    visible = client.get("/api/v1/classes", headers=owner_headers).json()
    assert len(visible) == 1
    assert visible[0]["id"] == active["id"]

    all_of_them = client.get("/api/v1/classes?include_inactive=true", headers=owner_headers).json()
    assert len(all_of_them) == 2


def test_list_available_to_staff(
    client: TestClient, owner_headers: dict, staff_headers: dict
) -> None:
    """Staff reads the catalog (needs it to sell passes, configure plans)."""
    _create_class(client, owner_headers, name="Pilates")
    r = client.get("/api/v1/classes", headers=staff_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_get_class_by_id(client: TestClient, owner_headers: dict) -> None:
    created = _create_class(client, owner_headers, name="CrossFit")
    r = client.get(f"/api/v1/classes/{created['id']}", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_class_not_found(client: TestClient, owner_headers: dict) -> None:
    r = client.get(f"/api/v1/classes/{uuid4()}", headers=owner_headers)
    assert r.status_code == 404


# ── Tenant scoping ────────────────────────────────────────────────────────────


def test_class_from_other_tenant_is_404(client: TestClient, owner_headers: dict) -> None:
    """Don't leak existence: gym A owner GETs gym B's class → 404, not 403.

    Critical security property — a 403 would confirm the class exists.
    """
    cls_a = _create_class(client, owner_headers, name="OnlyInA")

    # Build a second tenant + owner
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tb_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, 'B', :p, 'active') RETURNING id"
            ),
            {"s": f"b-{uuid4().hex[:8]}", "p": plan_id},
        ).scalar_one()
        ob_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": f"b-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1!cc"), "t": tb_id},
        ).scalar_one()
        session.commit()
    engine.dispose()
    tok_b = create_access_token(
        user_id=str(ob_id),
        role="owner",
        tenant_id=str(tb_id),
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    r = client.get(
        f"/api/v1/classes/{cls_a['id']}",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 404


# ── Update + lifecycle ────────────────────────────────────────────────────────


def test_update_class(client: TestClient, owner_headers: dict) -> None:
    c = _create_class(client, owner_headers, name="Old")
    r = client.patch(
        f"/api/v1/classes/{c['id']}",
        headers=owner_headers,
        json={"name": "New", "color": "#FF0000"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New"
    assert data["color"] == "#FF0000"


def test_update_to_colliding_name_returns_409(client: TestClient, owner_headers: dict) -> None:
    _create_class(client, owner_headers, name="Yoga")
    other = _create_class(client, owner_headers, name="Pilates")
    r = client.patch(
        f"/api/v1/classes/{other['id']}",
        headers=owner_headers,
        json={"name": "Yoga"},
    )
    assert r.status_code == 409


def test_staff_cannot_update(client: TestClient, owner_headers: dict, staff_headers: dict) -> None:
    """Staff reads the catalog but can't mutate it."""
    c = _create_class(client, owner_headers, name="Yoga")
    r = client.patch(f"/api/v1/classes/{c['id']}", headers=staff_headers, json={"name": "X"})
    assert r.status_code == 403


def test_deactivate_then_activate(client: TestClient, owner_headers: dict) -> None:
    c = _create_class(client, owner_headers, name="Spinning")

    r = client.post(f"/api/v1/classes/{c['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = client.post(f"/api/v1/classes/{c['id']}/activate", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_staff_cannot_deactivate(
    client: TestClient, owner_headers: dict, staff_headers: dict
) -> None:
    c = _create_class(client, owner_headers, name="Yoga")
    r = client.post(f"/api/v1/classes/{c['id']}/deactivate", headers=staff_headers)
    assert r.status_code == 403
