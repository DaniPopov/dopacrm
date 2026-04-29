"""E2E tests for the Convert flow — the atomic Member + Subscription
transaction.

Convert is the most important action in Leads and is the only path to
the ``converted`` terminal state. Rollback paths matter as much as the
happy path:

- Phone collision → MEMBER_ALREADY_EXISTS, lead stays put, no member
  inserted, no subscription inserted, no activity row.
- Cross-tenant plan id → 404, same rollback.
- Inactive plan → 409, same rollback.
- Already-converted lead → LEAD_ALREADY_CONVERTED, no writes.

Plus the happy path: lead → member with auto-filled fields + first
subscription against the picked plan + status_change activity row.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

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
    """Seed one tenant with leads enabled + an active monthly plan +
    owner / sales users."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = s.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status, features_enabled) "
                "VALUES (:s, 'G', :p, 'active', '{\"leads\": true}'::jsonb) RETURNING id"
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
        sales_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'sales', :t, true) RETURNING id"
            ),
            {"e": f"s-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
        ).scalar_one()
        membership_plan_id = s.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period, is_active) "
                "VALUES (:t, 'Monthly', 'recurring', 25000, 'ILS', 'monthly', true) "
                "RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        # Wildcard entitlement so the resulting member can attend.
        s.execute(
            text(
                "INSERT INTO plan_entitlements (plan_id, class_id, quantity, reset_period) "
                "VALUES (:p, NULL, NULL, 'unlimited')"
            ),
            {"p": membership_plan_id},
        )
        s.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_headers": _headers(owner_id, "owner", tenant_id, secret),
        "sales_headers": _headers(sales_id, "sales", tenant_id, secret),
        "plan_id": str(membership_plan_id),
    }


def _create_lead(client, headers, *, phone: str = "+972-50-555-0001"):
    r = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "first_name": "Yael",
            "last_name": "Cohen",
            "phone": phone,
            "email": "yael@example.com",
            "source": "walk_in",
            "notes": "Wants boxing, only Sundays.",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _count(table: str, *, tenant_id: str) -> int:
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        n = s.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),  # noqa: S608
            {"t": tenant_id},
        ).scalar_one()
    engine.dispose()
    return int(n)


# ── Happy path ──────────────────────────────────────────────────────


def test_sales_can_convert_to_member_and_subscription(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])

    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={
            "plan_id": env["plan_id"],
            "payment_method": "cash",
            "copy_notes_to_member": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Lead is now converted with a member id.
    assert body["lead"]["status"] == "converted"
    assert body["lead"]["converted_member_id"] == body["member"]["id"]

    # Member auto-filled from the lead.
    assert body["member"]["first_name"] == "Yael"
    assert body["member"]["last_name"] == "Cohen"
    assert body["member"]["phone"] == "+972-50-555-0001"
    assert body["member"]["email"] == "yael@example.com"
    assert body["member"]["notes"] == "Wants boxing, only Sundays."

    # Subscription wired to the plan, active.
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["plan_id"] == env["plan_id"]
    assert body["subscription"]["price_cents"] == 25000


def test_owner_can_convert(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["owner_headers"])
    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["owner_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r.status_code == 200


def test_convert_emits_status_change_activity(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    activities = client.get(
        f"/api/v1/leads/{lead['id']}/activities", headers=env["sales_headers"]
    ).json()
    converted = [a for a in activities if a["type"] == "status_change"]
    assert len(converted) == 1
    note = converted[0]["note"]
    assert "converted" in note
    assert "member=" in note


def test_convert_skips_notes_copy_when_flag_off(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={
            "plan_id": env["plan_id"],
            "payment_method": "cash",
            "copy_notes_to_member": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["member"]["notes"] is None


def test_convert_uses_explicit_start_date(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={
            "plan_id": env["plan_id"],
            "payment_method": "cash",
            "start_date": "2026-04-01",
        },
    )
    assert r.status_code == 200
    assert r.json()["subscription"]["started_at"] == "2026-04-01"


# ── Rollback paths ──────────────────────────────────────────────────


def test_phone_collision_rolls_back_everything(client: TestClient) -> None:
    """A member already exists with the lead's phone → 409. After
    rollback: no new member, no subscription, no activity, lead still
    NEW."""
    env = _seed()

    # Pre-existing member with the same phone.
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        s.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'Other', 'Person', '+972-50-555-0001')"
            ),
            {"t": env["tenant_id"]},
        )
        s.commit()
    engine.dispose()

    lead = _create_lead(client, env["sales_headers"], phone="+972-50-555-0001")

    members_before = _count("members", tenant_id=env["tenant_id"])
    subs_before = _count("subscriptions", tenant_id=env["tenant_id"])
    activities_before = _count("lead_activities", tenant_id=env["tenant_id"])

    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "MEMBER_ALREADY_EXISTS"

    # Counts unchanged — full rollback.
    assert _count("members", tenant_id=env["tenant_id"]) == members_before
    assert _count("subscriptions", tenant_id=env["tenant_id"]) == subs_before
    assert _count("lead_activities", tenant_id=env["tenant_id"]) == activities_before

    # Lead still in 'new' with no member linkage.
    after = client.get(f"/api/v1/leads/{lead['id']}", headers=env["sales_headers"]).json()
    assert after["status"] == "new"
    assert after["converted_member_id"] is None


def test_inactive_plan_rolls_back(client: TestClient) -> None:
    """Plan exists but is_active=false → 409. Whole convert rolls back."""
    env = _seed()
    # Deactivate the plan.
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        s.execute(
            text("UPDATE membership_plans SET is_active = false WHERE id = :p"),
            {"p": env["plan_id"]},
        )
        s.commit()
    engine.dispose()

    lead = _create_lead(client, env["sales_headers"])
    members_before = _count("members", tenant_id=env["tenant_id"])

    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r.status_code == 409

    assert _count("members", tenant_id=env["tenant_id"]) == members_before
    after = client.get(f"/api/v1/leads/{lead['id']}", headers=env["sales_headers"]).json()
    assert after["status"] == "new"


def test_unknown_plan_rolls_back(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    members_before = _count("members", tenant_id=env["tenant_id"])

    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": str(uuid4()), "payment_method": "cash"},
    )
    assert r.status_code == 404
    assert _count("members", tenant_id=env["tenant_id"]) == members_before


def test_already_converted_lead_rejected(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    r1 = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r1.status_code == 200

    # Second attempt fails.
    r2 = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "LEAD_ALREADY_CONVERTED"


# ── After convert, lead is terminal ─────────────────────────────────


def test_converted_lead_status_is_terminal(client: TestClient) -> None:
    """A converted lead can't be moved back via the simple status
    endpoint (terminal source)."""
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    r = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["sales_headers"],
        json={"new_status": "contacted"},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "INVALID_LEAD_STATUS_TRANSITION"


# ── Today's date defaults ───────────────────────────────────────────


def test_default_start_date_is_today(client: TestClient) -> None:
    env = _seed()
    lead = _create_lead(client, env["sales_headers"])
    r = client.post(
        f"/api/v1/leads/{lead['id']}/convert",
        headers=env["sales_headers"],
        json={"plan_id": env["plan_id"], "payment_method": "cash"},
    )
    assert r.status_code == 200
    assert r.json()["subscription"]["started_at"] == date.today().isoformat()
