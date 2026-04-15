"""E2E tests for ``GET /api/v1/admin/stats`` — the platform stats endpoint
that powers the super_admin dashboard.
"""

from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


# ── Happy-path: counts ────────────────────────────────────────────────────────


def test_platform_stats_empty_platform(client: TestClient, auth_headers: dict) -> None:
    """Fresh DB with only the seeded super_admin → tenant/member counts are 0.

    Confirms every aggregate query returns 0 cleanly on empty tables
    rather than null. The super_admin user itself is counted, so
    total_users is 1, not 0.
    """
    r = client.get("/api/v1/admin/stats", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data == {
        "total_tenants": 0,
        "active_tenants": 0,
        "new_tenants_this_month": 0,
        "total_users": 1,  # the seed super_admin
        "total_members": 0,
    }


def test_platform_stats_counts_tenants_and_users(client: TestClient, auth_headers: dict) -> None:
    """Create 2 tenants (both start on trial), verify counts reflect both.

    Trial tenants count as active because the service folds trial+active
    into ``active_tenants``. Also verifies "new this month" since new
    rows are created during the test (always within the current month).
    """
    for slug in ("gym-a", "gym-b"):
        r = client.post(
            "/api/v1/tenants", headers=auth_headers, json={"slug": slug, "name": slug.upper()}
        )
        assert r.status_code == 201

    r = client.get("/api/v1/admin/stats", headers=auth_headers)
    data = r.json()
    assert data["total_tenants"] == 2
    assert data["active_tenants"] == 2  # trial is active
    assert data["new_tenants_this_month"] == 2
    assert data["total_users"] == 1  # still just the seeded super_admin


def test_platform_stats_suspended_not_active(client: TestClient, auth_headers: dict) -> None:
    """Suspended tenants drop out of active_tenants but stay in total_tenants.

    Critical property — without this, suspending a gym wouldn't change
    the dashboard's "active gyms" number, which would defeat the point.
    """
    r = client.post("/api/v1/tenants", headers=auth_headers, json={"slug": "sus", "name": "S"})
    tid = r.json()["id"]
    client.post(f"/api/v1/tenants/{tid}/suspend", headers=auth_headers)

    r = client.get("/api/v1/admin/stats", headers=auth_headers)
    data = r.json()
    assert data["total_tenants"] == 1
    assert data["active_tenants"] == 0


def test_platform_stats_counts_members_across_tenants(
    client: TestClient, auth_headers: dict
) -> None:
    """Members in different tenants sum into total_members.

    Seeds two tenants, an owner each, and one member each — then
    confirms total_members == 2 regardless of which tenant they're in.
    """
    # Build two tenants + owners via the API + direct SQL (members can
    # only be created by tenant users, not super_admin)
    owner_tokens = []
    for slug in ("t1", "t2"):
        r = client.post("/api/v1/tenants", headers=auth_headers, json={"slug": slug, "name": slug})
        tid = r.json()["id"]

        engine = create_engine(_sync_url())
        with Session(engine) as session:
            owner_id = session.execute(
                text(
                    "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                    "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
                ),
                {"e": f"o-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1234!"), "t": tid},
            ).scalar_one()
            session.commit()
        engine.dispose()
        owner_tokens.append(
            create_access_token(
                user_id=str(owner_id),
                role="owner",
                tenant_id=tid,
                secret_key=os.environ["APP_SECRET_KEY"],
            )
        )

    for token in owner_tokens:
        r = client.post(
            "/api/v1/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"first_name": "M", "last_name": "X", "phone": f"+972-50-{uuid4().hex[:6]}"},
        )
        assert r.status_code == 201

    r = client.get("/api/v1/admin/stats", headers=auth_headers)
    data = r.json()
    assert data["total_tenants"] == 2
    assert data["total_members"] == 2
    assert data["total_users"] == 3  # super_admin + 2 owners


# ── Security ──────────────────────────────────────────────────────────────────


def test_platform_stats_super_admin_only(client: TestClient, auth_headers: dict) -> None:
    """Tenant-scoped users cannot hit /admin/stats — returns 403.

    Checks the require_super_admin guard on the route. A valid owner
    token for a real tenant still gets blocked.
    """
    # Seed a tenant + owner, try to read platform stats with owner token
    r = client.post("/api/v1/tenants", headers=auth_headers, json={"slug": "guarded", "name": "G"})
    tid = r.json()["id"]
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": "ow@g.co", "p": hash_password("Pass1234!"), "t": tid},
        ).scalar_one()
        session.commit()
    engine.dispose()
    token = create_access_token(
        user_id=str(owner_id),
        role="owner",
        tenant_id=tid,
        secret_key=os.environ["APP_SECRET_KEY"],
    )

    r = client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_platform_stats_requires_auth(client: TestClient) -> None:
    """No token at all → 401 (not 403). Baseline auth gate."""
    r = client.get("/api/v1/admin/stats")
    assert r.status_code == 401
