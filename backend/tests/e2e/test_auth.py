"""E2E tests for auth endpoints — login + security."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_success(client: TestClient, seed_super_admin: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 28800


def test_login_wrong_password(client: TestClient, seed_super_admin: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.com", "password": "anything"},
    )
    assert response.status_code == 401


def test_me_without_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)  # no auth → rejected


def test_me_with_token(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testadmin@test.com"
    assert data["role"] == "super_admin"


# ── Logout ────────────────────────────────────────────────────────────────────


def test_logout_with_token(client: TestClient, auth_headers: dict) -> None:
    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 204


def test_logout_without_token(client: TestClient) -> None:
    """Logout without auth should be rejected."""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code in (401, 403)


def test_logout_with_invalid_token(client: TestClient) -> None:
    """Logout with a garbage token should be rejected."""
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer invalid-garbage-token"},
    )
    assert response.status_code == 401


# ── SQL injection ─────────────────────────────────────────────────────────────


def test_sql_injection_in_email(client: TestClient) -> None:
    """Malicious email must be rejected — never 500 or 200."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "'; DROP TABLE users; --", "password": "anything"},
    )
    assert response.status_code in (401, 422)
    assert response.status_code != 500


def test_sql_injection_in_password(client: TestClient, seed_super_admin: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "' OR '1'='1"},
    )
    assert response.status_code == 401  # wrong password, not bypass


def test_sql_injection_union_select(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "' UNION SELECT * FROM users --", "password": "anything"},
    )
    assert response.status_code in (401, 422)
    assert response.status_code != 500
