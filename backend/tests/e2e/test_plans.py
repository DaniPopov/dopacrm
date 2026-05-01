"""E2E tests for Membership Plans endpoints + security + tenant scoping."""

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


def _auth_headers(user_id, role: str, tenant_id, secret: str) -> dict[str, str]:
    """Build a Bearer header for a tenant user — keeps fixture rows readable."""
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id),
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def gym_setup() -> dict:
    """Seed a tenant + owner + staff users. Returns ids + tokens."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, :n, :p, 'active') RETURNING id"
            ),
            {"s": f"gym-{uuid4().hex[:8]}", "n": "Gym", "p": plan_id},
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
        "owner_headers": _auth_headers(owner_id, "owner", tenant_id, secret),
        "staff_headers": _auth_headers(staff_id, "staff", tenant_id, secret),
    }


def _create_plan(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "name": "Monthly Unlimited",
        "type": "recurring",
        "price_cents": 25000,
        "currency": "ILS",
        "billing_period": "monthly",
        **overrides,
    }
    resp = client.post("/api/v1/plans", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_class(client: TestClient, headers: dict, name: str) -> dict:
    resp = client.post("/api/v1/classes", headers=headers, json={"name": name})
    assert resp.status_code == 201
    return resp.json()


# ── Create + permissions ─────────────────────────────────────────────────────


def test_owner_can_create_plan(client: TestClient, gym_setup: dict) -> None:
    data = _create_plan(client, gym_setup["owner_headers"])
    assert data["name"] == "Monthly Unlimited"
    assert data["price_cents"] == 25000
    assert data["is_active"] is True
    assert data["entitlements"] == []  # zero entitlements = unlimited any class


def test_staff_cannot_create_plan(client: TestClient, gym_setup: dict) -> None:
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["staff_headers"],
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
        },
    )
    assert r.status_code == 403


def test_super_admin_cannot_create_plan(client: TestClient, auth_headers: dict) -> None:
    """Platform-level role — blocked from gym-scoped plan ops."""
    r = client.post(
        "/api/v1/plans",
        headers=auth_headers,
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
        },
    )
    assert r.status_code == 403


def test_create_with_entitlements(client: TestClient, gym_setup: dict) -> None:
    """The user's real example: 3 group + 1 PT weekly."""
    group = _create_class(client, gym_setup["owner_headers"], "Group")
    pt = _create_class(client, gym_setup["owner_headers"], "PT")
    data = _create_plan(
        client,
        gym_setup["owner_headers"],
        name="3 group + 1 PT weekly",
        entitlements=[
            {"class_id": group["id"], "quantity": 3, "reset_period": "weekly"},
            {"class_id": pt["id"], "quantity": 1, "reset_period": "weekly"},
        ],
    )
    assert len(data["entitlements"]) == 2
    qs = sorted(e["quantity"] for e in data["entitlements"])
    assert qs == [1, 3]


# ── Shape validation ─────────────────────────────────────────────────────────


def test_create_recurring_with_duration_days_is_422(client: TestClient, gym_setup: dict) -> None:
    """recurring + duration_days is nonsense — service rejects with PLAN_INVALID_SHAPE."""
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
            "duration_days": 30,
        },
    )
    assert r.status_code == 422
    assert r.json()["error"] == "PLAN_INVALID_SHAPE"


def test_create_one_time_without_duration_days_is_422(client: TestClient, gym_setup: dict) -> None:
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "Drop-in",
            "type": "one_time",
            "price_cents": 4000,
            "billing_period": "one_time",
        },
    )
    assert r.status_code == 422


def test_create_one_time_with_wrong_billing_period_is_422(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "Drop-in",
            "type": "one_time",
            "price_cents": 4000,
            "billing_period": "monthly",
            "duration_days": 1,
        },
    )
    assert r.status_code == 422


def test_entitlement_unlimited_with_quantity_is_422(client: TestClient, gym_setup: dict) -> None:
    """unlimited entitlements can't have a quantity (contradictory)."""
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
            "entitlements": [{"class_id": None, "quantity": 3, "reset_period": "unlimited"}],
        },
    )
    assert r.status_code == 422


def test_entitlement_metered_without_quantity_is_422(client: TestClient, gym_setup: dict) -> None:
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
            "entitlements": [{"class_id": None, "quantity": None, "reset_period": "weekly"}],
        },
    )
    assert r.status_code == 422


def test_entitlement_class_from_other_tenant_is_422(
    client: TestClient, auth_headers: dict, gym_setup: dict
) -> None:
    """Can't reference a class that belongs to another tenant."""
    # super_admin creates a second tenant + an owner in it, who creates a class
    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": f"other-{uuid4().hex[:6]}", "name": "Other"},
    )
    other_tenant_id = resp.json()["id"]
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        other_owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {
                "e": f"ob-{uuid4().hex[:6]}@g.co",
                "p": hash_password("Pass1!cc"),
                "t": other_tenant_id,
            },
        ).scalar_one()
        session.commit()
    engine.dispose()
    other_owner_headers = _auth_headers(
        other_owner_id, "owner", other_tenant_id, os.environ["APP_SECRET_KEY"]
    )
    other_class = _create_class(client, other_owner_headers, "OtherClass")

    # Our tenant's owner tries to create a plan referencing that class
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "X",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
            "entitlements": [
                {
                    "class_id": other_class["id"],
                    "quantity": 1,
                    "reset_period": "weekly",
                }
            ],
        },
    )
    assert r.status_code == 422
    assert r.json()["error"] == "PLAN_INVALID_SHAPE"


# ── Read + list ──────────────────────────────────────────────────────────────


def test_list_plans_available_to_staff(client: TestClient, gym_setup: dict) -> None:
    """Staff can READ the catalog (needed to enroll members into plans)."""
    _create_plan(client, gym_setup["owner_headers"])
    r = client.get("/api/v1/plans", headers=gym_setup["staff_headers"])
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_excludes_inactive_by_default(client: TestClient, gym_setup: dict) -> None:
    created = _create_plan(client, gym_setup["owner_headers"])
    client.post(
        f"/api/v1/plans/{created['id']}/deactivate",
        headers=gym_setup["owner_headers"],
    )
    visible = client.get("/api/v1/plans", headers=gym_setup["owner_headers"]).json()
    assert len(visible) == 0

    all_of = client.get(
        "/api/v1/plans?include_inactive=true",
        headers=gym_setup["owner_headers"],
    ).json()
    assert len(all_of) == 1


def test_cross_tenant_plan_returns_404(
    client: TestClient, auth_headers: dict, gym_setup: dict
) -> None:
    """Fetching a plan from another tenant → 404 (not 403). No existence leak."""
    owner_plan = _create_plan(client, gym_setup["owner_headers"])

    resp = client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"slug": f"other-{uuid4().hex[:6]}", "name": "Other"},
    )
    other_tid = resp.json()["id"]
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        other_owner_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": f"x-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1!dd"), "t": other_tid},
        ).scalar_one()
        session.commit()
    engine.dispose()
    other_headers = _auth_headers(other_owner_id, "owner", other_tid, os.environ["APP_SECRET_KEY"])

    r = client.get(f"/api/v1/plans/{owner_plan['id']}", headers=other_headers)
    assert r.status_code == 404


# ── Update + lifecycle ──────────────────────────────────────────────────────


def test_update_replaces_entitlements(client: TestClient, gym_setup: dict) -> None:
    group = _create_class(client, gym_setup["owner_headers"], "Group")
    pt = _create_class(client, gym_setup["owner_headers"], "PT")
    plan = _create_plan(
        client,
        gym_setup["owner_headers"],
        entitlements=[{"class_id": group["id"], "quantity": 3, "reset_period": "weekly"}],
    )
    assert len(plan["entitlements"]) == 1

    r = client.patch(
        f"/api/v1/plans/{plan['id']}",
        headers=gym_setup["owner_headers"],
        json={"entitlements": [{"class_id": pt["id"], "quantity": 5, "reset_period": "monthly"}]},
    )
    assert r.status_code == 200
    updated = r.json()
    assert len(updated["entitlements"]) == 1
    assert updated["entitlements"][0]["class_id"] == pt["id"]
    assert updated["entitlements"][0]["quantity"] == 5


def test_update_without_entitlements_keeps_existing(client: TestClient, gym_setup: dict) -> None:
    """Omitting the key leaves existing rules alone — defensive for PATCH semantics."""
    group = _create_class(client, gym_setup["owner_headers"], "Group")
    plan = _create_plan(
        client,
        gym_setup["owner_headers"],
        entitlements=[{"class_id": group["id"], "quantity": 3, "reset_period": "weekly"}],
    )
    r = client.patch(
        f"/api/v1/plans/{plan['id']}",
        headers=gym_setup["owner_headers"],
        json={"price_cents": 50000},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["price_cents"] == 50000
    assert len(data["entitlements"]) == 1  # untouched


def test_update_with_empty_entitlements_clears(client: TestClient, gym_setup: dict) -> None:
    """Explicit empty list → clears entitlements (unlimited any class)."""
    group = _create_class(client, gym_setup["owner_headers"], "Group")
    plan = _create_plan(
        client,
        gym_setup["owner_headers"],
        entitlements=[{"class_id": group["id"], "quantity": 3, "reset_period": "weekly"}],
    )
    r = client.patch(
        f"/api/v1/plans/{plan['id']}",
        headers=gym_setup["owner_headers"],
        json={"entitlements": []},
    )
    assert r.json()["entitlements"] == []


def test_staff_cannot_update(client: TestClient, gym_setup: dict) -> None:
    plan = _create_plan(client, gym_setup["owner_headers"])
    r = client.patch(
        f"/api/v1/plans/{plan['id']}",
        headers=gym_setup["staff_headers"],
        json={"price_cents": 99999},
    )
    assert r.status_code == 403


def test_deactivate_then_activate(client: TestClient, gym_setup: dict) -> None:
    plan = _create_plan(client, gym_setup["owner_headers"])
    r = client.post(
        f"/api/v1/plans/{plan['id']}/deactivate",
        headers=gym_setup["owner_headers"],
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = client.post(
        f"/api/v1/plans/{plan['id']}/activate",
        headers=gym_setup["owner_headers"],
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_duplicate_name_in_tenant_returns_409(client: TestClient, gym_setup: dict) -> None:
    _create_plan(client, gym_setup["owner_headers"], name="Gold")
    r = client.post(
        "/api/v1/plans",
        headers=gym_setup["owner_headers"],
        json={
            "name": "Gold",
            "type": "recurring",
            "price_cents": 1,
            "billing_period": "monthly",
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "PLAN_ALREADY_EXISTS"
