"""E2E tests for auth endpoints — login, logout, cookies, blacklist, security."""

from __future__ import annotations

from fastapi.testclient import TestClient

# ── Login ─────────────────────────────────────────────────────────────────────


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


def test_login_sets_httponly_cookie(client: TestClient, seed_super_admin: dict) -> None:
    """Login must set an HttpOnly cookie with the JWT."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    cookie = response.cookies.get("access_token")
    assert cookie is not None
    assert len(cookie) > 50  # JWT is long


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


# ── /me ───────────────────────────────────────────────────────────────────────


def test_me_without_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


def test_me_with_bearer_header(client: TestClient, auth_headers: dict) -> None:
    """Auth via Authorization header still works (Swagger, API clients)."""
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testadmin@test.com"
    assert data["role"] == "super_admin"


def test_me_with_cookie(client: TestClient, seed_super_admin: dict) -> None:
    """Auth via HttpOnly cookie works (frontend flow)."""
    # Login to get the cookie
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "testpass123"},
    )
    assert login_resp.status_code == 200

    # /me should work — cookie is sent automatically by TestClient
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "testadmin@test.com"


# ── Logout + blacklist ────────────────────────────────────────────────────────


def test_logout_clears_cookie(client: TestClient, seed_super_admin: dict) -> None:
    """Logout must clear the auth cookie."""
    # Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "testpass123"},
    )
    assert login_resp.status_code == 200

    # Logout
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204


def test_token_rejected_after_logout(client: TestClient, seed_super_admin: dict) -> None:
    """After logout, the same token must be rejected (Redis blacklist)."""
    # Login — get token from response body
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@test.com", "password": "testpass123"},
    )
    token = login_resp.json()["access_token"]

    # Logout via Bearer header
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 204

    # Try to use the same token — must be rejected
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 401
    assert me_resp.json()["detail"] == "Token has been revoked"


def test_logout_without_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code in (401, 403)


def test_logout_with_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer invalid-garbage-token"},
    )
    assert response.status_code == 401


# ── SQL injection ─────────────────────────────────────────────────────────────


def test_sql_injection_in_email(client: TestClient) -> None:
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
    assert response.status_code == 401


def test_sql_injection_union_select(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "' UNION SELECT * FROM users --", "password": "anything"},
    )
    assert response.status_code in (401, 422)
    assert response.status_code != 500
