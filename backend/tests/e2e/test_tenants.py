"""E2E tests for tenant CRUD endpoints + security.

Tests cover:
- Happy-path CRUD (create, list, get, update, suspend)
- Permission enforcement (non-super_admin roles blocked)
- Duplicate slug handling
- SQL injection attempts
- Token manipulation
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.security import create_access_token

# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_tenant(client: TestClient, auth_headers: dict, slug: str = "test-gym") -> dict:
    """Helper: create a tenant and return the response data."""
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": slug, "name": f"Test Gym ({slug})"},
    )
    assert resp.status_code == 201
    return resp.json()


# ── CRUD ─────────────────────────────────────────────────────────────────────


def test_create_tenant(client: TestClient, auth_headers: dict) -> None:
    data = _create_tenant(client, auth_headers, slug="ironfit-tlv")
    assert data["slug"] == "ironfit-tlv"
    assert data["name"] == "Test Gym (ironfit-tlv)"
    assert data["status"] == "active"
    assert data["timezone"] == "Asia/Jerusalem"
    assert data["currency"] == "ILS"
    assert data["locale"] == "he-IL"
    assert data["trial_ends_at"] is None
    assert "id" in data


def test_create_tenant_with_custom_fields(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={
            "slug": "la-gym",
            "name": "Muscle Beach LA",
            "phone": "+1-310-555-0000",
            "timezone": "America/Los_Angeles",
            "currency": "USD",
            "locale": "en-US",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["timezone"] == "America/Los_Angeles"
    assert data["currency"] == "USD"


def test_list_tenants(client: TestClient, auth_headers: dict) -> None:
    _create_tenant(client, auth_headers, slug="list-gym-1")
    _create_tenant(client, auth_headers, slug="list-gym-2")
    resp = client.get("/api/v1/tenants", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


def test_get_tenant_by_id(client: TestClient, auth_headers: dict) -> None:
    created = _create_tenant(client, auth_headers, slug="get-me")
    resp = client.get(f"/api/v1/tenants/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["slug"] == "get-me"


def test_get_tenant_not_found(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_update_tenant(client: TestClient, auth_headers: dict) -> None:
    created = _create_tenant(client, auth_headers, slug="update-me")
    resp = client.patch(
        f"/api/v1/tenants/{created['id']}",
        headers=auth_headers,
        json={"name": "Updated Gym Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Gym Name"
    assert resp.json()["slug"] == "update-me"  # unchanged


def test_suspend_tenant(client: TestClient, auth_headers: dict) -> None:
    created = _create_tenant(client, auth_headers, slug="suspend-me")
    assert created["status"] == "active"
    resp = client.post(
        f"/api/v1/tenants/{created['id']}/suspend",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


def test_duplicate_slug_returns_409(client: TestClient, auth_headers: dict) -> None:
    _create_tenant(client, auth_headers, slug="unique-slug")
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": "unique-slug", "name": "Duplicate"},
    )
    assert resp.status_code == 409


# ── Permission enforcement (non-super_admin roles) ──────────────────────────


def _make_token(role: str, tenant_id: str | None = None) -> str:
    """Create a JWT for a given role."""
    return create_access_token(
        user_id="00000000-0000-0000-0000-000000000001",
        role=role,
        tenant_id=tenant_id,
        secret_key=os.environ["APP_SECRET_KEY"],
    )


def _role_headers(role: str, tenant_id: str = "550e8400-e29b-41d4-a716-446655440000") -> dict:
    return {"Authorization": f"Bearer {_make_token(role, tenant_id)}"}


def test_owner_cannot_create_tenant(client: TestClient) -> None:
    """Gym owners must NOT be able to onboard new tenants."""
    resp = client.post(
        "/api/v1/tenants",
        headers=_role_headers("owner"),
        json={"slug": "hack-gym", "name": "Hacked"},
    )
    assert resp.status_code == 403


def test_staff_cannot_create_tenant(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/tenants",
        headers=_role_headers("staff"),
        json={"slug": "hack-gym", "name": "Hacked"},
    )
    assert resp.status_code == 403


def test_sales_cannot_create_tenant(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/tenants",
        headers=_role_headers("sales"),
        json={"slug": "hack-gym", "name": "Hacked"},
    )
    assert resp.status_code == 403


def test_owner_cannot_list_tenants(client: TestClient) -> None:
    """Gym owners must NOT see the full tenant list."""
    resp = client.get("/api/v1/tenants", headers=_role_headers("owner"))
    assert resp.status_code == 403


def test_owner_cannot_update_tenant(client: TestClient, auth_headers: dict) -> None:
    """Gym owners must NOT update tenant records."""
    created = _create_tenant(client, auth_headers, slug="no-update")
    resp = client.patch(
        f"/api/v1/tenants/{created['id']}",
        headers=_role_headers("owner"),
        json={"name": "Hacked Name"},
    )
    assert resp.status_code == 403


def test_owner_cannot_suspend_tenant(client: TestClient, auth_headers: dict) -> None:
    """Gym owners must NOT be able to suspend any tenant (including their own)."""
    created = _create_tenant(client, auth_headers, slug="no-suspend")
    resp = client.post(
        f"/api/v1/tenants/{created['id']}/suspend",
        headers=_role_headers("owner"),
    )
    assert resp.status_code == 403


def test_staff_cannot_suspend_tenant(client: TestClient, auth_headers: dict) -> None:
    created = _create_tenant(client, auth_headers, slug="no-staff-suspend")
    resp = client.post(
        f"/api/v1/tenants/{created['id']}/suspend",
        headers=_role_headers("staff"),
    )
    assert resp.status_code == 403


# ── Auth required ────────────────────────────────────────────────────────────


def test_create_tenant_without_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/tenants",
        json={"slug": "no-auth", "name": "No Auth"},
    )
    assert resp.status_code in (401, 403)


def test_list_tenants_without_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/tenants")
    assert resp.status_code in (401, 403)


def test_suspend_without_auth(client: TestClient) -> None:
    resp = client.post("/api/v1/tenants/00000000-0000-0000-0000-000000000000/suspend")
    assert resp.status_code in (401, 403)


# ── Token manipulation ──────────────────────────────────────────────────────


def test_forged_super_admin_token_rejected(client: TestClient) -> None:
    """JWT signed with wrong key claiming super_admin must be rejected."""
    forged_token = create_access_token(
        user_id="00000000-0000-0000-0000-000000000000",
        role="super_admin",
        tenant_id=None,
        secret_key="wrong-key-attacker-doesnt-know",
    )
    resp = client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {forged_token}"},
        json={"slug": "forged", "name": "Forged"},
    )
    assert resp.status_code == 401


# ── SQL injection ────────────────────────────────────────────────────────────


def test_sql_injection_in_tenant_id(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(
        "/api/v1/tenants/'; DROP TABLE tenants; --",
        headers=auth_headers,
    )
    assert resp.status_code == 422  # FastAPI rejects invalid UUID


def test_sql_injection_in_slug(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": "'; DELETE FROM tenants; --", "name": "Evil"},
    )
    # Should either succeed (slug is just a string) or fail validation,
    # but NEVER 500 or actually execute the SQL
    assert resp.status_code != 500


def test_xss_in_tenant_name(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": "xss-gym", "name": "<script>alert('xss')</script>"},
    )
    # The name is stored as-is (output encoding is the frontend's job),
    # but should not cause a server error
    assert resp.status_code in (201, 422)
    assert resp.status_code != 500
