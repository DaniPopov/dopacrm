"""E2E tests for the Leads API.

Covers:
- Feature flag gate (every endpoint returns 403 FEATURE_DISABLED when off)
- CRUD happy paths
- State machine — legal moves + auto status_change activity row
- Drag-to-converted via simple status PATCH is rejected (must use convert)
- Activities — append-only, status_change is system-only (422 from clients),
  blank notes rejected (422)
- Lost-reason capture + autocomplete
- Stats endpoint
- Permissions: staff is read-only; sales/owner can write
- Convert flow lives in test_lead_convert.py — its own file because
  the txn rollback paths warrant focused coverage.

Cross-tenant probes live in test_cross_tenant_isolation.py — this file
is the in-tenant happy-path coverage.
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


def _headers(user_id, role, tenant_id, secret):
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id) if tenant_id else None,
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed(*, leads_enabled: bool = True) -> dict:
    """Seed one tenant + owner + sales + staff + coach users; optional Leads on."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        features = '{"leads": true}' if leads_enabled else "{}"
        tenant_id = s.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status, features_enabled) "
                "VALUES (:s, 'G', :p, 'active', CAST(:f AS jsonb)) RETURNING id"
            ),
            {"s": f"t-{uuid4().hex[:8]}", "p": plan_id, "f": features},
        ).scalar_one()

        users: dict[str, str] = {}
        for role in ("owner", "sales", "staff", "coach"):
            uid = s.execute(
                text(
                    "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                    "VALUES (:e, :p, :r, :t, true) RETURNING id"
                ),
                {
                    "e": f"{role}-{uuid4().hex[:6]}@g.co",
                    "p": hash_password("x"),
                    "r": role,
                    "t": tenant_id,
                },
            ).scalar_one()
            users[role] = uid

        s.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_id": str(users["owner"]),
        "sales_id": str(users["sales"]),
        "owner_headers": _headers(users["owner"], "owner", tenant_id, secret),
        "sales_headers": _headers(users["sales"], "sales", tenant_id, secret),
        "staff_headers": _headers(users["staff"], "staff", tenant_id, secret),
        "coach_headers": _headers(users["coach"], "coach", tenant_id, secret),
    }


# ── Feature flag gate ────────────────────────────────────────────────


def test_disabled_returns_403_on_create(client: TestClient) -> None:
    env = _seed(leads_enabled=False)
    r = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "FEATURE_DISABLED"


def test_disabled_returns_403_on_list(client: TestClient) -> None:
    env = _seed(leads_enabled=False)
    r = client.get("/api/v1/leads", headers=env["owner_headers"])
    assert r.status_code == 403
    assert r.json()["error"] == "FEATURE_DISABLED"


def test_disabled_returns_403_on_stats(client: TestClient) -> None:
    env = _seed(leads_enabled=False)
    r = client.get("/api/v1/leads/stats", headers=env["owner_headers"])
    assert r.status_code == 403


def test_disabled_returns_403_on_lost_reasons(client: TestClient) -> None:
    env = _seed(leads_enabled=False)
    r = client.get("/api/v1/leads/lost-reasons", headers=env["owner_headers"])
    assert r.status_code == 403


def test_feature_off_blocks_every_endpoint_and_writes_nothing(
    client: TestClient,
) -> None:
    """Lockdown audit — when ``leads`` is OFF for the tenant, every one
    of the 11 endpoints must 403 with FEATURE_DISABLED, and nothing
    must be written to leads / lead_activities / members / subscriptions.

    Especially important for convert: its happy path writes 4 rows
    across 4 tables in one transaction. A feature-flag check that runs
    AFTER any of those writes would silently leak data. This test seeds
    an existing lead + plan via raw SQL (bypassing the API entirely),
    flips the tenant flag OFF, runs every mutation, and asserts
    counts haven't moved.
    """
    # Seed two tenants — one with the flag ON to insert a lead + plan via
    # raw SQL, one we'll then flip OFF to probe.
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        # Insert tenant with leads ON, owner, an existing lead, and a plan
        # the convert endpoint can pick.
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
        membership_plan_id = s.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period, is_active) "
                "VALUES (:t, 'Monthly', 'recurring', 25000, 'ILS', 'monthly', true) "
                "RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        s.execute(
            text(
                "INSERT INTO plan_entitlements (plan_id, class_id, quantity, reset_period) "
                "VALUES (:p, NULL, NULL, 'unlimited')"
            ),
            {"p": membership_plan_id},
        )
        existing_lead_id = s.execute(
            text(
                "INSERT INTO leads (tenant_id, first_name, last_name, phone, source) "
                "VALUES (:t, 'Existing', 'Lead', '+972-50-555-9999', 'walk_in') "
                "RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        # NOW flip the flag OFF — every API call below should 403.
        s.execute(
            text("UPDATE tenants SET features_enabled = '{\"leads\": false}'::jsonb WHERE id = :t"),
            {"t": tenant_id},
        )
        s.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    headers = _headers(owner_id, "owner", tenant_id, secret)
    tenant_id_str = str(tenant_id)
    lead_id = str(existing_lead_id)
    plan_id_str = str(membership_plan_id)

    def _count(table: str) -> int:
        eng = create_engine(_sync_url())
        with Session(eng) as ss:
            n = ss.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),  # noqa: S608
                {"t": tenant_id_str},
            ).scalar_one()
        eng.dispose()
        return int(n)

    # Snapshot row counts across every table the leads feature could
    # mutate. After hitting every endpoint, all four must be unchanged.
    before = {
        "leads": _count("leads"),
        "lead_activities": _count("lead_activities"),
        "members": _count("members"),
        "subscriptions": _count("subscriptions"),
    }

    # Every endpoint, mutation + read alike. Reads also check that the
    # gate runs FIRST — otherwise a 403 might come from a downstream
    # role check and we'd lose the FEATURE_DISABLED contract.
    probes = [
        # (method, path, json or None)
        ("POST", "/api/v1/leads", {"first_name": "A", "last_name": "B", "phone": "+1"}),
        ("GET", "/api/v1/leads", None),
        ("GET", "/api/v1/leads/stats", None),
        ("GET", "/api/v1/leads/lost-reasons", None),
        ("GET", f"/api/v1/leads/{lead_id}", None),
        ("PATCH", f"/api/v1/leads/{lead_id}", {"notes": "trying to write"}),
        (
            "POST",
            f"/api/v1/leads/{lead_id}/status",
            {"new_status": "contacted"},
        ),
        ("POST", f"/api/v1/leads/{lead_id}/assign", {"user_id": None}),
        (
            "POST",
            f"/api/v1/leads/{lead_id}/convert",
            {"plan_id": plan_id_str, "payment_method": "cash"},
        ),
        ("GET", f"/api/v1/leads/{lead_id}/activities", None),
        (
            "POST",
            f"/api/v1/leads/{lead_id}/activities",
            {"type": "note", "note": "trying to write"},
        ),
    ]

    for method, path, body in probes:
        if method == "GET":
            r = client.get(path, headers=headers)
        elif method == "POST":
            r = client.post(path, headers=headers, json=body)
        elif method == "PATCH":
            r = client.patch(path, headers=headers, json=body)
        else:
            raise AssertionError(f"unhandled method: {method}")
        assert r.status_code == 403, (
            f"{method} {path} expected 403 with leads off, got {r.status_code}: {r.text}"
        )
        assert r.json()["error"] == "FEATURE_DISABLED", (
            f"{method} {path} expected FEATURE_DISABLED code, got {r.json()}"
        )

    # Nothing got written.
    after = {
        "leads": _count("leads"),
        "lead_activities": _count("lead_activities"),
        "members": _count("members"),
        "subscriptions": _count("subscriptions"),
    }
    assert before == after, f"row counts changed under feature-off: {before} → {after}"


# ── CRUD ─────────────────────────────────────────────────────────────


def test_owner_can_create_and_list(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={
            "first_name": "Yael",
            "last_name": "Cohen",
            "phone": "+972-50-123-4567",
            "source": "walk_in",
            "notes": "Asked about boxing",
        },
    )
    assert r.status_code == 201
    lead = r.json()
    assert lead["first_name"] == "Yael"
    assert lead["status"] == "new"
    assert lead["source"] == "walk_in"

    r2 = client.get("/api/v1/leads", headers=env["owner_headers"])
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_sales_can_create(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/leads",
        headers=env["sales_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    )
    assert r.status_code == 201


def test_staff_cannot_create_but_can_read(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/leads",
        headers=env["staff_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    )
    assert r.status_code == 403

    # Staff CAN read.
    r2 = client.get("/api/v1/leads", headers=env["staff_headers"])
    assert r2.status_code == 200


def test_coach_blocked_from_reads_too(client: TestClient) -> None:
    env = _seed()
    r = client.get("/api/v1/leads", headers=env["coach_headers"])
    assert r.status_code == 403


def test_get_one_lead(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.get(f"/api/v1/leads/{created['id']}", headers=env["owner_headers"])
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_returns_404(client: TestClient) -> None:
    env = _seed()
    r = client.get(f"/api/v1/leads/{uuid4()}", headers=env["owner_headers"])
    assert r.status_code == 404


def test_update_lead_strips_protected_fields(client: TestClient) -> None:
    """status / converted_member_id / lost_reason can't be PATCHed
    directly — they go through the dedicated endpoints. PATCH ignores
    them silently (Pydantic doesn't expose them on UpdateLeadRequest)."""
    env = _seed()
    created = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()

    r = client.patch(
        f"/api/v1/leads/{created['id']}",
        headers=env["owner_headers"],
        json={
            "notes": "follow up tuesday",
            # Pydantic's UpdateLeadRequest doesn't accept these fields,
            # so they're silently dropped.
            "status": "converted",
            "converted_member_id": str(uuid4()),
        },
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "follow up tuesday"
    assert r.json()["status"] == "new"  # unchanged
    assert r.json()["converted_member_id"] is None


def test_assign_to_user_in_same_tenant(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{created['id']}/assign",
        headers=env["owner_headers"],
        json={"user_id": env["sales_id"]},
    )
    assert r.status_code == 200
    assert r.json()["assigned_to"] == env["sales_id"]


def test_assign_to_unknown_user_returns_404(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{created['id']}/assign",
        headers=env["owner_headers"],
        json={"user_id": str(uuid4())},
    )
    assert r.status_code == 404


def test_unassign_via_null(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    client.post(
        f"/api/v1/leads/{created['id']}/assign",
        headers=env["owner_headers"],
        json={"user_id": env["sales_id"]},
    )
    r = client.post(
        f"/api/v1/leads/{created['id']}/assign",
        headers=env["owner_headers"],
        json={"user_id": None},
    )
    assert r.status_code == 200
    assert r.json()["assigned_to"] is None


# ── State machine ───────────────────────────────────────────────────


def test_status_transitions_emit_status_change_activity(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "contacted"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "contacted"

    # Activity log should have a status_change entry.
    activities = client.get(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["owner_headers"],
    ).json()
    assert any(
        a["type"] == "status_change" and "new" in a["note"] and "contacted" in a["note"]
        for a in activities
    )


def test_drag_to_converted_via_status_endpoint_rejected(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "converted"},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "INVALID_LEAD_STATUS_TRANSITION"


def test_lost_then_reopen_clears_lost_reason(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()

    # New → lost (with reason)
    r1 = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "lost", "lost_reason": "too expensive"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "lost"
    assert r1.json()["lost_reason"] == "too expensive"

    # Lost → contacted (reopen). Column cleared, history kept.
    r2 = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "contacted"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "contacted"
    assert r2.json()["lost_reason"] is None

    # The historical "lost" activity still has the reason in its note.
    activities = client.get(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["owner_headers"],
    ).json()
    lost_activity = next(a for a in activities if "lost" in a["note"] and "reason" in a["note"])
    assert "too expensive" in lost_activity["note"]


def test_illegal_transition_returns_409(client: TestClient) -> None:
    """new → trial → contacted is allowed (trial didn't happen).
    Then contacted → new is NOT allowed (no backward path)."""
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "contacted"},
    )

    r = client.post(
        f"/api/v1/leads/{lead['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "new"},
    )
    assert r.status_code == 409


# ── Activities ──────────────────────────────────────────────────────


def test_add_call_activity(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["owner_headers"],
        json={"type": "call", "note": "Left voicemail. Will retry Tuesday."},
    )
    assert r.status_code == 201
    assert r.json()["type"] == "call"
    assert r.json()["created_by"] == env["owner_id"]


def test_status_change_type_rejected_at_parse(client: TestClient) -> None:
    """Schema-level validator — clients can't fabricate audit rows."""
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["owner_headers"],
        json={"type": "status_change", "note": "fake row"},
    )
    assert r.status_code == 422


def test_blank_note_rejected(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["owner_headers"],
        json={"type": "note", "note": "   "},
    )
    assert r.status_code == 422


def test_staff_cannot_add_activity(client: TestClient) -> None:
    env = _seed()
    lead = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        headers=env["staff_headers"],
        json={"type": "note", "note": "x"},
    )
    assert r.status_code == 403


# ── Lost reasons / stats ────────────────────────────────────────────


def test_lost_reasons_autocomplete(client: TestClient) -> None:
    env = _seed()
    # Three leads with the same reason in different cases — collapsed.
    for i in range(3):
        lead = client.post(
            "/api/v1/leads",
            headers=env["owner_headers"],
            json={
                "first_name": "A",
                "last_name": "B",
                "phone": f"+972-50-000-{i:04d}",
            },
        ).json()
        client.post(
            f"/api/v1/leads/{lead['id']}/status",
            headers=env["owner_headers"],
            json={"new_status": "lost", "lost_reason": "Too Expensive"},
        )

    r = client.get("/api/v1/leads/lost-reasons", headers=env["owner_headers"])
    assert r.status_code == 200
    rows = r.json()
    assert any(row["reason"] == "too expensive" and row["count"] == 3 for row in rows)


def test_stats_includes_zero_filled_counts(client: TestClient) -> None:
    env = _seed()
    # Two leads — one new, one lost.
    a = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+1"},
    ).json()
    b = client.post(
        "/api/v1/leads",
        headers=env["owner_headers"],
        json={"first_name": "B", "last_name": "C", "phone": "+2"},
    ).json()
    # leave `a` as new, mark `b` lost
    client.post(
        f"/api/v1/leads/{b['id']}/status",
        headers=env["owner_headers"],
        json={"new_status": "lost", "lost_reason": "x"},
    )
    _ = a  # noqa — only used for clarity

    r = client.get("/api/v1/leads/stats", headers=env["owner_headers"])
    assert r.status_code == 200
    body = r.json()
    # Every status key present, zero-filled.
    for s in ("new", "contacted", "trial", "converted", "lost"):
        assert s in body["counts"]
    assert body["counts"]["new"] == 1
    assert body["counts"]["lost"] == 1
    assert body["counts"]["contacted"] == 0
    # No converts → conversion rate = 0.0 (not None) since denominator is 2 created.
    assert body["conversion_rate_30d"] == 0.0


def test_stats_conversion_rate_none_when_no_leads(client: TestClient) -> None:
    env = _seed()
    r = client.get("/api/v1/leads/stats", headers=env["owner_headers"])
    assert r.status_code == 200
    assert r.json()["conversion_rate_30d"] is None
