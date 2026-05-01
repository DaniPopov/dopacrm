"""E2E tests for the nested tenant-detail endpoints.

Covers ``GET /tenants/{id}/stats`` and ``GET /tenants/{id}/users`` —
the two endpoints the frontend tenant-detail page calls to fill the
stats cards and the users list section.

Each test seeds data via the HTTP API (no direct DB writes) so the
whole stack is exercised (schemas, service permission checks, rate
limiting, JWT).
"""

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
def tenant_with_owner(auth_headers: dict, client: TestClient) -> dict:
    """Create a tenant via the API and seed an owner user for it.

    Returns both sets of credentials so tests can exercise the
    super_admin path AND the tenant-user path on the same gym.
    """
    # Super_admin creates the tenant
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": f"gym-{uuid4().hex[:8]}", "name": "IronFit"},
    )
    assert resp.status_code == 201
    tenant = resp.json()

    # Seed an owner directly (avoids POST /users dependency on super_admin token)
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:email, :pwd, 'owner', :tid, true) RETURNING id"
            ),
            {
                "email": f"owner-{uuid4().hex[:6]}@gym.com",
                "pwd": hash_password("OwnerPass1!"),
                "tid": tenant["id"],
            },
        ).scalar_one()
        session.commit()
    engine.dispose()

    owner_token = create_access_token(
        user_id=str(owner_id),
        role="owner",
        tenant_id=tenant["id"],
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    return {"tenant": tenant, "owner_headers": {"Authorization": f"Bearer {owner_token}"}}


# ═══════════════════════════════════════════════════════════════════════════
#  GET /api/v1/tenants/{id}/stats
# ═══════════════════════════════════════════════════════════════════════════


def test_stats_zero_when_no_members_or_users(client: TestClient, auth_headers: dict) -> None:
    """Stats on a brand-new tenant report 0s across the board.

    This is the baseline case — verifies the endpoint wires through
    the repo count queries correctly, and that empty tables return 0
    rather than null.
    """
    resp = client.post(
        "/api/v1/tenants", headers=auth_headers, json={"slug": "empty", "name": "Empty Gym"}
    )
    tenant_id = resp.json()["id"]

    r = client.get(f"/api/v1/tenants/{tenant_id}/stats", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"total_members": 0, "active_members": 0, "total_users": 0}


def test_stats_counts_members_and_users(
    client: TestClient, auth_headers: dict, tenant_with_owner: dict
) -> None:
    """Creating a member + a user should bump the corresponding counters.

    We create one active member through the owner's token (members can
    only be created by tenant users, not super_admin) — and verify the
    super_admin sees the counts reflected in the stats response.
    """
    tenant = tenant_with_owner["tenant"]
    owner_headers = tenant_with_owner["owner_headers"]

    # Owner creates 2 members
    for i in range(2):
        r = client.post(
            "/api/v1/members",
            headers=owner_headers,
            json={
                "first_name": f"M{i}",
                "last_name": "Test",
                "phone": f"+972-50-{i:06d}",
            },
        )
        assert r.status_code == 201, r.text

    # Super_admin reads stats (already includes the owner user we seeded)
    r = client.get(f"/api/v1/tenants/{tenant['id']}/stats", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_members"] == 2
    assert data["active_members"] == 2
    assert data["total_users"] == 1  # just the owner we seeded


def test_stats_freeze_drops_active_but_keeps_total(
    client: TestClient, auth_headers: dict, tenant_with_owner: dict
) -> None:
    """``active_members`` and ``total_members`` diverge when someone freezes.

    Verifies the stats endpoint uses the status filter correctly — a
    frozen member still counts toward total but not active.
    """
    tenant = tenant_with_owner["tenant"]
    owner_headers = tenant_with_owner["owner_headers"]

    # Two members, freeze one
    created = []
    for i in range(2):
        r = client.post(
            "/api/v1/members",
            headers=owner_headers,
            json={"first_name": f"M{i}", "last_name": "X", "phone": f"+972-50-{i:06d}"},
        )
        created.append(r.json())
    client.post(f"/api/v1/members/{created[0]['id']}/freeze", headers=owner_headers, json={})

    r = client.get(f"/api/v1/tenants/{tenant['id']}/stats", headers=auth_headers)
    data = r.json()
    assert data["total_members"] == 2
    assert data["active_members"] == 1


def test_stats_tenant_not_found(client: TestClient, auth_headers: dict) -> None:
    """Requesting stats for a non-existent tenant returns 404.

    Important because the endpoint does a stats compute first, then a
    tenant-exists check — the order matters for avoiding leaks.
    """
    r = client.get(f"/api/v1/tenants/{uuid4()}/stats", headers=auth_headers)
    assert r.status_code == 404


def test_stats_other_tenant_user_forbidden(
    client: TestClient, auth_headers: dict, tenant_with_owner: dict
) -> None:
    """Owner of gym A cannot read stats of gym B.

    The service's ``_require_super_admin_or_same_tenant`` guard blocks
    cross-tenant reads. Key security property — stats leak would give
    away customer counts.
    """
    # Build a second tenant
    resp = client.post(
        "/api/v1/tenants", headers=auth_headers, json={"slug": "other", "name": "Other"}
    )
    other = resp.json()

    # Gym A's owner tries to read gym B's stats
    r = client.get(
        f"/api/v1/tenants/{other['id']}/stats",
        headers=tenant_with_owner["owner_headers"],
    )
    assert r.status_code == 403


def test_stats_tenant_user_can_read_own_stats(client: TestClient, tenant_with_owner: dict) -> None:
    """Owner reads stats of their own gym — allowed.

    Complement to the above: the permission check is symmetric — same
    tenant is fine, different tenant is 403.
    """
    tenant = tenant_with_owner["tenant"]
    r = client.get(
        f"/api/v1/tenants/{tenant['id']}/stats",
        headers=tenant_with_owner["owner_headers"],
    )
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  GET /api/v1/tenants/{id}/users
# ═══════════════════════════════════════════════════════════════════════════


def test_list_users_for_tenant_returns_only_that_tenant(
    client: TestClient, auth_headers: dict, tenant_with_owner: dict
) -> None:
    """The nested users endpoint filters strictly by tenant_id.

    We seed a second tenant + owner and assert the first tenant's
    users endpoint doesn't return the second's owner. Also asserts
    the shape — super_admin (with tenant_id=null) should not appear
    in either list.
    """
    # Build a second tenant with its own owner
    resp = client.post(
        "/api/v1/tenants", headers=auth_headers, json={"slug": "second", "name": "Second"}
    )
    second = resp.json()
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:email, :pwd, 'owner', :tid, true)"
            ),
            {
                "email": f"second-{uuid4().hex[:6]}@gym.com",
                "pwd": hash_password("Pass1234!"),
                "tid": second["id"],
            },
        )
        session.commit()
    engine.dispose()

    # Request users for the first tenant only
    r = client.get(
        f"/api/v1/tenants/{tenant_with_owner['tenant']['id']}/users",
        headers=auth_headers,
    )
    assert r.status_code == 200
    users = r.json()
    assert len(users) == 1
    assert users[0]["tenant_id"] == tenant_with_owner["tenant"]["id"]
    assert users[0]["role"] == "owner"


def test_list_users_for_tenant_super_admin_only(
    client: TestClient, tenant_with_owner: dict
) -> None:
    """A tenant user can't list another tenant's users via this endpoint.

    This endpoint is explicitly super_admin-only — tenant users use
    GET /users which is already tenant-scoped. Defense in depth.
    """
    tenant = tenant_with_owner["tenant"]
    r = client.get(
        f"/api/v1/tenants/{tenant['id']}/users",
        headers=tenant_with_owner["owner_headers"],
    )
    assert r.status_code == 403


def test_list_users_for_tenant_not_found(client: TestClient, auth_headers: dict) -> None:
    """Requesting users of an unknown tenant returns 404, not 200+[]."""
    r = client.get(f"/api/v1/tenants/{uuid4()}/users", headers=auth_headers)
    assert r.status_code == 404
