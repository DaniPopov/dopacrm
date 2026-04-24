"""E2E tests for super_admin resetting a user's password.

``PATCH /api/v1/users/{id}`` with ``password=<new_pwd>`` hashes the new
value in the service layer and overwrites ``password_hash``. The round-
trip is end-to-end: verify the user CAN login with the new password
and CANNOT with the old one.
"""

from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import hash_password


def _sync_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _seed_user_in_tenant(email: str, old_password: str) -> tuple[str, str]:
    """Create a tenant + one owner user via direct SQL. Returns (tenant_id, user_id)."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:slug, 'T', :plan, 'active') RETURNING id"
            ),
            {"slug": f"t-{uuid4().hex[:8]}", "plan": plan_id},
        ).scalar_one()
        user_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": email, "p": hash_password(old_password), "t": tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()
    return str(tenant_id), str(user_id)


def test_password_reset_allows_new_login(client: TestClient, auth_headers: dict) -> None:
    """Super_admin PATCHes a user's password → user can log in with the new one.

    The happy path end-to-end: seed a user with an old password, PATCH
    via super_admin token to set a new one, then try the login endpoint
    with the NEW password and confirm success.
    """
    email = f"reset-{uuid4().hex[:6]}@gym.com"
    _, user_id = _seed_user_in_tenant(email, "OldPass1!")

    # Super_admin resets the password
    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=auth_headers,
        json={"password": "NewPass1!"},
    )
    assert resp.status_code == 200

    # New password works
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "NewPass1!"})
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_old_password_rejected_after_reset(client: TestClient, auth_headers: dict) -> None:
    """After a password reset, the old password no longer works.

    Complements the above — without this, the "new password works"
    test could still pass even if the service never actually overwrote
    the hash (edge case: both hashes valid somehow). This asserts the
    old one is DEAD.
    """
    email = f"reset2-{uuid4().hex[:6]}@gym.com"
    _, user_id = _seed_user_in_tenant(email, "OldPass1!")

    client.patch(
        f"/api/v1/users/{user_id}",
        headers=auth_headers,
        json={"password": "NewPass1!"},
    )

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "OldPass1!"})
    assert login.status_code == 401


def test_update_without_password_keeps_old_password(client: TestClient, auth_headers: dict) -> None:
    """Updating other fields (e.g. first_name) must NOT wipe the password.

    Defensive: verifies the service only hashes when ``password`` is in
    the payload — not when it's merely omitted from a partial update.
    """
    email = f"no-reset-{uuid4().hex[:6]}@gym.com"
    _, user_id = _seed_user_in_tenant(email, "OrigPass1!")

    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=auth_headers,
        json={"first_name": "Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Renamed"

    # Original password still works
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "OrigPass1!"})
    assert login.status_code == 200


def test_password_reset_enforces_min_length(client: TestClient, auth_headers: dict) -> None:
    """Passwords shorter than 8 chars are rejected — same rule as create.

    Only length is enforced today. Character-class complexity (uppercase,
    special) was dropped 2026-04-24 to keep onboarding friction low;
    rely on 8-char minimum + argon2 hashing + rate-limited login.
    """
    _, user_id = _seed_user_in_tenant(f"short-{uuid4().hex[:6]}@gym.com", "OldPass1!")

    r = client.patch(
        f"/api/v1/users/{user_id}",
        headers=auth_headers,
        json={"password": "short"},
    )
    assert r.status_code == 422


def test_password_reset_accepts_simple_password(client: TestClient, auth_headers: dict) -> None:
    """All-lowercase, no-special-char passwords work as long as len >= 8.

    Locks in the "complexity removed" decision — if someone re-adds the
    validator, this test fails.
    """
    email = f"simple-{uuid4().hex[:6]}@gym.com"
    _, user_id = _seed_user_in_tenant(email, "OldPass1!")

    resp = client.patch(
        f"/api/v1/users/{user_id}",
        headers=auth_headers,
        json={"password": "lowercase"},
    )
    assert resp.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "lowercase"})
    assert login.status_code == 200


def test_password_reset_requires_auth(client: TestClient) -> None:
    """No token → 401, not 403. Baseline gate before permission check."""
    _, user_id = _seed_user_in_tenant(f"anon-{uuid4().hex[:6]}@gym.com", "OldPass1!")
    r = client.patch(f"/api/v1/users/{user_id}", json={"password": "NewPass1!"})
    assert r.status_code == 401
