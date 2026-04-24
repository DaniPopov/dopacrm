"""E2E tests for the Coaches API.

Covers happy paths across the 12 endpoints:
- Coach CRUD + freeze/unfreeze/cancel + invite-user
- Class ↔ coach link assign / patch / delete / list-by-class / list-by-coach
- Earnings per-coach + earnings summary
- Attendance coach attribution + reassign-coach

Cross-tenant probes live in ``test_cross_tenant_isolation.py`` — this
file is the in-tenant happy-path coverage that the isolation suite
relies on being correct.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _headers(user_id, role, tenant_id, secret):
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id) if tenant_id else None,
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed() -> dict:
    """Seed one tenant + owner + staff + a class + a member + a live sub."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = s.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, 'G', :p, 'active') RETURNING id"
            ),
            {"s": f"t-{uuid4().hex[:8]}", "p": plan_id},
        ).scalar_one()
        owner_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": f"o-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
        ).scalar_one()
        staff_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'staff', :t, true) RETURNING id"
            ),
            {"e": f"s-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
        ).scalar_one()
        class_id = s.execute(
            text("INSERT INTO classes (tenant_id, name) VALUES (:t, 'Boxing') RETURNING id"),
            {"t": tenant_id},
        ).scalar_one()
        member_id = s.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'M', 'X', :ph) RETURNING id"
            ),
            {"t": tenant_id, "ph": f"05{uuid4().hex[:8]}"},
        ).scalar_one()
        plan_pid = s.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period) "
                "VALUES (:t, 'Monthly', 'recurring', 25000, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        # Wildcard entitlement so the member can attend any class.
        s.execute(
            text(
                "INSERT INTO plan_entitlements "
                "(plan_id, class_id, quantity, reset_period) "
                "VALUES (:p, NULL, NULL, 'unlimited')"
            ),
            {"p": plan_pid},
        )
        s.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, started_at) "
                "VALUES (:t, :m, :p, 'active', 25000, 'ILS', :s)"
            ),
            {"t": tenant_id, "m": member_id, "p": plan_pid, "s": date.today()},
        )
        s.commit()
    engine.dispose()
    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_headers": _headers(owner_id, "owner", tenant_id, secret),
        "staff_headers": _headers(staff_id, "staff", tenant_id, secret),
        "class_id": str(class_id),
        "member_id": str(member_id),
    }


# ── Coach CRUD ────────────────────────────────────────────────────────


def test_owner_can_create_and_list_a_coach(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "David", "last_name": "Cohen"},
    )
    assert r.status_code == 201
    coach = r.json()
    assert coach["first_name"] == "David"
    assert coach["status"] == "active"

    r2 = client.get("/api/v1/coaches", headers=env["owner_headers"])
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_staff_cannot_create_coach(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/coaches",
        headers=env["staff_headers"],
        json={"first_name": "X", "last_name": "Y"},
    )
    assert r.status_code == 403


def test_owner_can_freeze_unfreeze_cancel(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()

    frozen = client.post(
        f"/api/v1/coaches/{coach['id']}/freeze", headers=env["owner_headers"]
    ).json()
    assert frozen["status"] == "frozen"

    unfrozen = client.post(
        f"/api/v1/coaches/{coach['id']}/unfreeze", headers=env["owner_headers"]
    ).json()
    assert unfrozen["status"] == "active"

    cancelled = client.post(
        f"/api/v1/coaches/{coach['id']}/cancel", headers=env["owner_headers"]
    ).json()
    assert cancelled["status"] == "cancelled"


def test_invite_user_creates_login(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    r = client.post(
        f"/api/v1/coaches/{coach['id']}/invite-user",
        headers=env["owner_headers"],
        json={
            "email": f"coach-{uuid4().hex[:6]}@gym.com",
            "password": "initialpass",
        },
    )
    assert r.status_code == 200
    assert r.json()["user_id"] is not None


def test_invite_user_rejects_already_linked(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    email1 = f"c1-{uuid4().hex[:6]}@gym.com"
    email2 = f"c2-{uuid4().hex[:6]}@gym.com"
    client.post(
        f"/api/v1/coaches/{coach['id']}/invite-user",
        headers=env["owner_headers"],
        json={"email": email1, "password": "initialpass"},
    )
    r = client.post(
        f"/api/v1/coaches/{coach['id']}/invite-user",
        headers=env["owner_headers"],
        json={"email": email2, "password": "initialpass"},
    )
    assert r.status_code == 409


# ── Class-coach links ─────────────────────────────────────────────────


def test_assign_coach_to_class(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    r = client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json={
            "coach_id": coach["id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "per_attendance",
            "pay_amount_cents": 5000,
            "weekdays": ["sun", "tue"],
            "starts_on": "2026-01-01",
        },
    )
    assert r.status_code == 201
    link = r.json()
    assert link["pay_model"] == "per_attendance"
    assert set(link["weekdays"]) == {"sun", "tue"}

    listed = client.get(
        f"/api/v1/classes/{env['class_id']}/coaches", headers=env["owner_headers"]
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_duplicate_role_returns_409(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    body = {
        "coach_id": coach["id"],
        "role": "ראשי",
        "is_primary": True,
        "pay_model": "fixed",
        "pay_amount_cents": 300000,
        "weekdays": [],
    }
    assert (
        client.post(
            f"/api/v1/classes/{env['class_id']}/coaches",
            headers=env["owner_headers"],
            json=body,
        ).status_code
        == 201
    )
    r = client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json=body,
    )
    assert r.status_code == 409


def test_patch_and_delete_link(client: TestClient) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    link = client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json={
            "coach_id": coach["id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "fixed",
            "pay_amount_cents": 200000,
            "weekdays": [],
        },
    ).json()

    r = client.patch(
        f"/api/v1/class-coaches/{link['id']}",
        headers=env["owner_headers"],
        json={"pay_amount_cents": 250000},
    )
    assert r.status_code == 200
    assert r.json()["pay_amount_cents"] == 250000

    r2 = client.delete(
        f"/api/v1/class-coaches/{link['id']}", headers=env["owner_headers"]
    )
    assert r2.status_code == 204


# ── Attendance attribution + earnings ─────────────────────────────────


def test_attendance_attributes_coach_and_earnings_counts(
    client: TestClient,
) -> None:
    env = _seed()
    coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    # Weekdays=[] so it matches today whatever day it is.
    client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json={
            "coach_id": coach["id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "per_attendance",
            "pay_amount_cents": 5000,
            "weekdays": [],
            "starts_on": "2026-01-01",
        },
    )
    # Record a check-in.
    r = client.post(
        "/api/v1/attendance",
        headers=env["staff_headers"],
        json={"member_id": env["member_id"], "class_id": env["class_id"]},
    )
    assert r.status_code == 201
    entry = r.json()
    assert entry["coach_id"] == coach["id"]

    # Earnings should reflect the one attendance.
    today = date.today().isoformat()
    r2 = client.get(
        f"/api/v1/coaches/{coach['id']}/earnings?from={today}&to={today}",
        headers=env["owner_headers"],
    )
    assert r2.status_code == 200
    bd = r2.json()
    assert bd["total_cents"] == 5000
    assert bd["currency"] in {"ILS", "USD", "EUR"}
    assert len(bd["by_link"]) == 1
    assert bd["by_link"][0]["cents"] == 5000
    assert bd["by_link"][0]["unit_count"] == 1


def test_owner_can_reassign_coach_on_entry(client: TestClient) -> None:
    env = _seed()
    coach_a = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "Coach"},
    ).json()
    coach_b = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "B", "last_name": "Coach"},
    ).json()
    client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json={
            "coach_id": coach_a["id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "fixed",
            "pay_amount_cents": 10000,
            "weekdays": [],
            "starts_on": "2026-01-01",
        },
    )
    entry = client.post(
        "/api/v1/attendance",
        headers=env["staff_headers"],
        json={"member_id": env["member_id"], "class_id": env["class_id"]},
    ).json()
    assert entry["coach_id"] == coach_a["id"]

    r = client.post(
        f"/api/v1/attendance/{entry['id']}/reassign-coach",
        headers=env["owner_headers"],
        json={"coach_id": coach_b["id"]},
    )
    assert r.status_code == 200
    assert r.json()["coach_id"] == coach_b["id"]


def test_earnings_summary_includes_all_active_coaches(
    client: TestClient,
) -> None:
    env = _seed()
    for name in ("A", "B"):
        client.post(
            "/api/v1/coaches",
            headers=env["owner_headers"],
            json={"first_name": name, "last_name": "C"},
        )
    r = client.get(
        "/api/v1/coaches/earnings/summary?from=2026-05-01&to=2026-05-31",
        headers=env["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_earnings_range_inverted_rejected(client: TestClient) -> None:
    env = _seed()
    c = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "D", "last_name": "C"},
    ).json()
    r = client.get(
        f"/api/v1/coaches/{c['id']}/earnings?from=2026-05-31&to=2026-05-01",
        headers=env["owner_headers"],
    )
    assert r.status_code == 422
