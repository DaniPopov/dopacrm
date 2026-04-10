"""E2E tests for user CRUD endpoints + security."""

from __future__ import annotations

from fastapi.testclient import TestClient

# ── CRUD ──────────────────────────────────────────────────────────────────────


def test_create_super_admin_user(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "email": "new-super@test.com",
            "password": "LongSecure@Pass123",
            "role": "super_admin",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new-super@test.com"
    assert data["role"] == "super_admin"
    assert data["is_active"] is True
    assert "password" not in data
    assert "password_hash" not in data


def test_list_users(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/v1/users", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_user_not_found(client: TestClient, auth_headers: dict) -> None:
    response = client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_delete_user(client: TestClient, auth_headers: dict) -> None:
    # Create
    create_resp = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "email": "todelete@test.com",
            "password": "Delete@Me12345",
            "role": "super_admin",
        },
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Soft-delete
    del_resp = client.delete(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Verify soft-deleted
    get_resp = client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


# ── Auth required ─────────────────────────────────────────────────────────────


def test_create_user_without_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users",
        json={"email": "x@x.com", "password": "test12345", "role": "super_admin"},
    )
    assert response.status_code in (401, 403)


def test_list_users_without_auth(client: TestClient) -> None:
    response = client.get("/api/v1/users")
    assert response.status_code in (401, 403)


# ── Role escalation ──────────────────────────────────────────────────────────


def test_sales_cannot_create_user(client: TestClient, seed_super_admin: dict) -> None:
    """A sales user with a VALID token must not be able to create users (super_admin only)."""
    import os

    from app.core.security import create_access_token

    sales_token = create_access_token(
        user_id=seed_super_admin["id"],
        role="sales",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {sales_token}"},
        json={"email": "hack@evil.com", "password": "test12345678", "role": "super_admin"},
    )
    assert response.status_code == 403


def test_staff_cannot_delete_user(client: TestClient, seed_super_admin: dict) -> None:
    """A staff user with a VALID token must not be able to delete users (owner+ only)."""
    import os

    from app.core.security import create_access_token

    staff_token = create_access_token(
        user_id=seed_super_admin["id"],
        role="staff",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    response = client.delete(
        f"/api/v1/users/{seed_super_admin['id']}",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert response.status_code == 403


def test_forged_role_escalation_rejected(client: TestClient) -> None:
    """JWT with role manually changed to super_admin but signed with wrong key → 401."""
    from app.core.security import create_access_token

    forged_token = create_access_token(
        user_id="00000000-0000-0000-0000-000000000000",
        role="super_admin",
        tenant_id=None,
        secret_key="wrong-key-attacker-doesnt-know-real-secret",
    )
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401


# ── Token manipulation ────────────────────────────────────────────────────────


def test_tampered_jwt_is_rejected(client: TestClient) -> None:
    """A JWT with a modified payload (different signature) must be rejected."""
    fake_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIiwicm9sZSI6InN1cGVyX2FkbWluIn0.invalid"
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert response.status_code == 401


def test_owner_with_null_tenant_cannot_list_users(
    client: TestClient, seed_super_admin: dict
) -> None:
    """Defense-in-depth: a non-super_admin token with tenant_id=None must
    be rejected (403), not return all users."""
    import os

    from app.core.security import create_access_token

    bad_token = create_access_token(
        user_id=seed_super_admin["id"],
        role="owner",
        tenant_id=None,
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert response.status_code == 403


# ── SQL injection ─────────────────────────────────────────────────────────────


def test_sql_injection_in_user_id(client: TestClient, auth_headers: dict) -> None:
    response = client.get(
        "/api/v1/users/'; DROP TABLE users; --",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_sql_injection_in_create_email(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "email": "'; DELETE FROM users; --@evil.com",
            "password": "test12345678",
            "role": "super_admin",
        },
    )
    assert response.status_code == 422


def test_xss_in_email(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "email": "<script>alert('xss')</script>@evil.com",
            "password": "test12345678",
            "role": "super_admin",
        },
    )
    assert response.status_code == 422
