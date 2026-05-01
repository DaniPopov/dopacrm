"""Cross-tenant isolation — the SECURITY audit.

Every gym-scoped endpoint must reject access to another tenant's data.
The expected response is **404 Not Found** (not 403) for most
reads/mutations so we don't leak the existence of a resource across
tenants. Some cross-tenant combinations on create/enroll surface as
**422** (e.g., "plan and member belong to different tenants") because
the payload itself is malformed rather than the resource being missing.

This file seeds TWO separate tenants (A and B), each with their own
member / class / plan / active subscription / recorded entry, then
uses A's staff/owner tokens to probe every gym-scoped endpoint with
B's IDs. Everything must 404 or 4xx-reject — never 200/201/OK with
B's data.

If any test here fails, DO NOT paper over it. A green test means:
"A's staff absolutely cannot read or mutate B's data through this
endpoint, even with a forged ID."

The tests use every role variant (owner, staff, sales) where
applicable so we don't accidentally open cross-tenant access to a
subset of roles.
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

# ── helpers ──────────────────────────────────────────────────────────────────


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _headers(user_id, role: str, tenant_id, secret: str) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id) if tenant_id else None,
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(session: Session, saas_plan_id) -> dict:
    """Seed a minimal tenant with owner+staff+sales, one member, one
    class, one plan, one active subscription, and one recorded entry."""
    tenant_id = session.execute(
        text(
            "INSERT INTO tenants (slug, name, saas_plan_id, status) "
            "VALUES (:s, 'Gym', :p, 'active') RETURNING id"
        ),
        {"s": f"t-{uuid4().hex[:8]}", "p": saas_plan_id},
    ).scalar_one()
    owner_id = session.execute(
        text(
            "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
            "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
        ),
        {"e": f"o-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
    ).scalar_one()
    staff_id = session.execute(
        text(
            "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
            "VALUES (:e, :p, 'staff', :t, true) RETURNING id"
        ),
        {"e": f"s-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
    ).scalar_one()
    sales_id = session.execute(
        text(
            "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
            "VALUES (:e, :p, 'sales', :t, true) RETURNING id"
        ),
        {"e": f"sa-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
    ).scalar_one()
    member_id = session.execute(
        text(
            "INSERT INTO members (tenant_id, first_name, last_name, phone) "
            "VALUES (:t, 'M', 'X', :ph) RETURNING id"
        ),
        {"t": tenant_id, "ph": f"05{uuid4().hex[:8]}"},
    ).scalar_one()
    class_id = session.execute(
        text("INSERT INTO classes (tenant_id, name) VALUES (:t, 'Yoga') RETURNING id"),
        {"t": tenant_id},
    ).scalar_one()
    plan_id = session.execute(
        text(
            "INSERT INTO membership_plans "
            "(tenant_id, name, type, price_cents, currency, billing_period) "
            "VALUES (:t, 'Monthly', 'recurring', 25000, 'ILS', 'monthly') RETURNING id"
        ),
        {"t": tenant_id},
    ).scalar_one()
    sub_id = session.execute(
        text(
            "INSERT INTO subscriptions "
            "(tenant_id, member_id, plan_id, status, price_cents, currency, started_at) "
            "VALUES (:t, :m, :p, 'active', 25000, 'ILS', :s) RETURNING id"
        ),
        {"t": tenant_id, "m": member_id, "p": plan_id, "s": date.today()},
    ).scalar_one()
    entry_id = session.execute(
        text(
            "INSERT INTO class_entries "
            "(tenant_id, member_id, subscription_id, class_id, entered_by) "
            "VALUES (:t, :m, :sub, :c, :u) RETURNING id"
        ),
        {
            "t": tenant_id,
            "m": member_id,
            "sub": sub_id,
            "c": class_id,
            "u": staff_id,
        },
    ).scalar_one()
    coach_id = session.execute(
        text(
            "INSERT INTO coaches "
            "(tenant_id, first_name, last_name) "
            "VALUES (:t, 'C', 'Oach') RETURNING id"
        ),
        {"t": tenant_id},
    ).scalar_one()
    link_id = session.execute(
        text(
            "INSERT INTO class_coaches "
            "(tenant_id, class_id, coach_id, role, is_primary, pay_model, "
            " pay_amount_cents, weekdays) "
            "VALUES (:t, :c, :k, 'ראשי', true, 'per_attendance', 5000, "
            " ARRAY[]::text[]) RETURNING id"
        ),
        {"t": tenant_id, "c": class_id, "k": coach_id},
    ).scalar_one()
    # Enable Schedule + Leads for both tenants so the isolation probes can hit
    # those endpoints; without the flag we'd get 403 instead of
    # 404 and the test wouldn't exercise tenant scoping.
    session.execute(
        text(
            "UPDATE tenants SET features_enabled = "
            '\'{"coaches": true, "schedule": true, "leads": true}\'::jsonb '
            "WHERE id = :t"
        ),
        {"t": tenant_id},
    )
    template_id = session.execute(
        text(
            "INSERT INTO class_schedule_templates "
            "(tenant_id, class_id, weekdays, start_time, end_time, "
            " head_coach_id) "
            "VALUES (:t, :c, ARRAY['sun']::text[], '18:00', '19:00', :k) "
            "RETURNING id"
        ),
        {"t": tenant_id, "c": class_id, "k": coach_id},
    ).scalar_one()
    session_row_id = session.execute(
        text(
            "INSERT INTO class_sessions "
            "(tenant_id, class_id, template_id, starts_at, ends_at, "
            " head_coach_id, status) "
            "VALUES (:t, :c, :tpl, '2026-05-17T15:00:00Z', "
            " '2026-05-17T16:00:00Z', :k, 'scheduled') RETURNING id"
        ),
        {"t": tenant_id, "c": class_id, "tpl": template_id, "k": coach_id},
    ).scalar_one()
    lead_id = session.execute(
        text(
            "INSERT INTO leads (tenant_id, first_name, last_name, phone, source) "
            "VALUES (:t, 'Lead', 'Person', :ph, 'walk_in') RETURNING id"
        ),
        {"t": tenant_id, "ph": f"05{uuid4().hex[:8]}"},
    ).scalar_one()
    activity_id = session.execute(
        text(
            "INSERT INTO lead_activities (tenant_id, lead_id, type, note) "
            "VALUES (:t, :l, 'note', 'first contact') RETURNING id"
        ),
        {"t": tenant_id, "l": lead_id},
    ).scalar_one()
    return {
        "tenant_id": str(tenant_id),
        "owner_id": str(owner_id),
        "staff_id": str(staff_id),
        "sales_id": str(sales_id),
        "member_id": str(member_id),
        "class_id": str(class_id),
        "plan_id": str(plan_id),
        "sub_id": str(sub_id),
        "entry_id": str(entry_id),
        "coach_id": str(coach_id),
        "class_coach_id": str(link_id),
        "template_id": str(template_id),
        "session_id": str(session_row_id),
        "lead_id": str(lead_id),
        "activity_id": str(activity_id),
    }


@pytest.fixture
def two_gyms() -> dict:
    """Seed two separate tenants + return both sets of IDs + headers."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        saas_plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        a = _seed_tenant(session, saas_plan_id)
        b = _seed_tenant(session, saas_plan_id)
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "a": {
            **a,
            "owner_headers": _headers(a["owner_id"], "owner", a["tenant_id"], secret),
            "staff_headers": _headers(a["staff_id"], "staff", a["tenant_id"], secret),
            "sales_headers": _headers(a["sales_id"], "sales", a["tenant_id"], secret),
        },
        "b": b,  # B's IDs only — we use A's tokens to probe them
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Members — staff in A tries to touch B's member
# ══════════════════════════════════════════════════════════════════════════════


def test_staff_cannot_read_foreign_member(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/members/{two_gyms['b']['member_id']}",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 404


def test_staff_cannot_update_foreign_member(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/members/{two_gyms['b']['member_id']}",
        headers=two_gyms["a"]["staff_headers"],
        json={"first_name": "Hijacked"},
    )
    assert r.status_code == 404


def test_sales_cannot_read_foreign_member(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/members/{two_gyms['b']['member_id']}",
        headers=two_gyms["a"]["sales_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_update_foreign_member(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/members/{two_gyms['b']['member_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"first_name": "Hijacked"},
    )
    assert r.status_code == 404


def test_members_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    """Sanity: listing members only returns A's member — B's member
    exists but must never appear here."""
    r = client.get("/api/v1/members", headers=two_gyms["a"]["staff_headers"])
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()}
    assert two_gyms["a"]["member_id"] in ids
    assert two_gyms["b"]["member_id"] not in ids


# ══════════════════════════════════════════════════════════════════════════════
#  Classes — owner-only mutations
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_read_foreign_class(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/classes/{two_gyms['b']['class_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_deactivate_foreign_class(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/classes/{two_gyms['b']['class_id']}/deactivate",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_update_foreign_class(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/classes/{two_gyms['b']['class_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"name": "Hijacked"},
    )
    assert r.status_code == 404


def test_classes_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/classes", headers=two_gyms["a"]["staff_headers"])
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert two_gyms["a"]["class_id"] in ids
    assert two_gyms["b"]["class_id"] not in ids


# ══════════════════════════════════════════════════════════════════════════════
#  Membership Plans — owner-only mutations
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_read_foreign_plan(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/plans/{two_gyms['b']['plan_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_update_foreign_plan(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/plans/{two_gyms['b']['plan_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"price_cents": 1},
    )
    assert r.status_code == 404


def test_owner_cannot_deactivate_foreign_plan(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/plans/{two_gyms['b']['plan_id']}/deactivate",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_plans_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/plans", headers=two_gyms["a"]["staff_headers"])
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert two_gyms["a"]["plan_id"] in ids
    assert two_gyms["b"]["plan_id"] not in ids


# ══════════════════════════════════════════════════════════════════════════════
#  Subscriptions — all 6 state-transition endpoints + create
# ══════════════════════════════════════════════════════════════════════════════


def test_cannot_create_sub_with_foreign_member(client: TestClient, two_gyms: dict) -> None:
    """A's staff tries to enroll B's member on A's plan.
    Service detects member-tenant mismatch → 422."""
    r = client.post(
        "/api/v1/subscriptions",
        headers=two_gyms["a"]["staff_headers"],
        json={
            "member_id": two_gyms["b"]["member_id"],
            "plan_id": two_gyms["a"]["plan_id"],
        },
    )
    assert r.status_code in (404, 422)


def test_cannot_create_sub_with_foreign_plan(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        "/api/v1/subscriptions",
        headers=two_gyms["a"]["staff_headers"],
        json={
            "member_id": two_gyms["a"]["member_id"],
            "plan_id": two_gyms["b"]["plan_id"],
        },
    )
    assert r.status_code == 422


def test_staff_cannot_read_foreign_sub(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 404


def test_staff_cannot_freeze_foreign_sub(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/freeze",
        headers=two_gyms["a"]["staff_headers"],
        json={},
    )
    assert r.status_code == 404


def test_staff_cannot_unfreeze_foreign_sub(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/unfreeze",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 404


def test_staff_cannot_renew_foreign_sub(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/renew",
        headers=two_gyms["a"]["staff_headers"],
        json={},
    )
    assert r.status_code == 404


def test_staff_cannot_change_foreign_sub_plan(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/change-plan",
        headers=two_gyms["a"]["staff_headers"],
        json={"new_plan_id": two_gyms["a"]["plan_id"]},
    )
    assert r.status_code == 404


def test_staff_cannot_cancel_foreign_sub(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/cancel",
        headers=two_gyms["a"]["staff_headers"],
        json={},
    )
    assert r.status_code == 404


def test_sub_events_cross_tenant_is_404(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/subscriptions/{two_gyms['b']['sub_id']}/events",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 404


def test_subs_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/subscriptions", headers=two_gyms["a"]["staff_headers"])
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert two_gyms["a"]["sub_id"] in ids
    assert two_gyms["b"]["sub_id"] not in ids


# ══════════════════════════════════════════════════════════════════════════════
#  Attendance — record + undo + reads
# ══════════════════════════════════════════════════════════════════════════════


def test_cannot_record_entry_for_foreign_member(client: TestClient, two_gyms: dict) -> None:
    """A's staff tries to check in B's member on A's class.
    Service sees B's member has no live sub in A's tenant → 409."""
    r = client.post(
        "/api/v1/attendance",
        headers=two_gyms["a"]["staff_headers"],
        json={
            "member_id": two_gyms["b"]["member_id"],
            "class_id": two_gyms["a"]["class_id"],
        },
    )
    # Service calls find_live_for_member(A_tenant, B_member) → None → 409
    # The exact 409 code is MEMBER_NO_ACTIVE_SUBSCRIPTION (not a 404) because
    # A has no sub for B's member in A's scope. Either way, no cross-tenant
    # data leaks.
    assert r.status_code == 409


def test_quota_check_for_foreign_member_is_blocked(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/attendance/quota-check"
        f"?member_id={two_gyms['b']['member_id']}"
        f"&class_id={two_gyms['a']['class_id']}",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 409


def test_staff_cannot_undo_foreign_entry(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/attendance/{two_gyms['b']['entry_id']}/undo",
        headers=two_gyms["a"]["staff_headers"],
        json={},
    )
    assert r.status_code == 404


def test_attendance_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/attendance", headers=two_gyms["a"]["staff_headers"])
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert two_gyms["a"]["entry_id"] in ids
    assert two_gyms["b"]["entry_id"] not in ids


def test_member_attendance_for_foreign_member_returns_empty(
    client: TestClient, two_gyms: dict
) -> None:
    """A foreign member id doesn't return B's entries — it returns
    whatever A has for that id (which is nothing, because the member
    isn't in A's tenant)."""
    r = client.get(
        f"/api/v1/attendance/members/{two_gyms['b']['member_id']}",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


def test_member_summary_for_foreign_member_returns_empty(
    client: TestClient, two_gyms: dict
) -> None:
    r = client.get(
        f"/api/v1/attendance/members/{two_gyms['b']['member_id']}/summary",
        headers=two_gyms["a"]["staff_headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


# ══════════════════════════════════════════════════════════════════════════════
#  Tenants — owner can't read/write another tenant via tenants endpoint
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_read_foreign_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/tenants/{two_gyms['b']['tenant_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    # Tenants endpoint is super_admin-only for reads; owner gets 403 or 404
    assert r.status_code in (403, 404)


def test_owner_cannot_suspend_foreign_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/tenants/{two_gyms['b']['tenant_id']}/suspend",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code in (403, 404)


# ══════════════════════════════════════════════════════════════════════════════
#  Users — owner can't list another tenant's users
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_list_foreign_tenant_users(client: TestClient, two_gyms: dict) -> None:
    """Platform users endpoint: /users is super_admin + owner, scoped
    to caller's tenant. Owner in A should see A's users only — B's
    three users must never appear."""
    r = client.get("/api/v1/users", headers=two_gyms["a"]["owner_headers"])
    # Owner of A can list users in A (their own tenant only)
    assert r.status_code == 200
    ids = {u["id"] for u in r.json()}
    assert two_gyms["b"]["owner_id"] not in ids
    assert two_gyms["b"]["staff_id"] not in ids
    assert two_gyms["b"]["sales_id"] not in ids


def test_owner_cannot_read_foreign_tenant_user_by_id(client: TestClient, two_gyms: dict) -> None:
    """Previously a leak: GET /users/{id} didn't scope by caller tenant.
    Owner in A could fetch any user's record (email / role / name /
    phone). Now returns 404 — same pattern as the tenants leak."""
    r = client.get(
        f"/api/v1/users/{two_gyms['b']['staff_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_update_foreign_tenant_user(client: TestClient, two_gyms: dict) -> None:
    """Previously a leak: PATCH /users/{id} let owner in A modify users
    in B — could have rotated a foreign tenant's owner password. Fix
    enforces tenant-scoped access; foreign ID → 404."""
    r = client.patch(
        f"/api/v1/users/{two_gyms['b']['staff_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"first_name": "Hijacked"},
    )
    assert r.status_code == 404


def test_owner_cannot_delete_foreign_tenant_user(client: TestClient, two_gyms: dict) -> None:
    """Previously a leak: DELETE /users/{id} let owner in A disable any
    other tenant's users. Now 404."""
    r = client.delete(
        f"/api/v1/users/{two_gyms['b']['staff_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
#  Coaches + class_coaches + earnings + reassign-coach
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_read_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_update_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"first_name": "Hijacked"},
    )
    assert r.status_code == 404


def test_owner_cannot_freeze_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}/freeze",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_cancel_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}/cancel",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_coaches_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/coaches", headers=two_gyms["a"]["owner_headers"])
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert two_gyms["a"]["coach_id"] in ids
    assert two_gyms["b"]["coach_id"] not in ids


def test_owner_cannot_list_classes_of_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}/classes",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_query_foreign_coach_earnings(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/coaches/{two_gyms['b']['coach_id']}/earnings?from=2026-05-01&to=2026-05-31",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_earnings_summary_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        "/api/v1/coaches/earnings/summary?from=2026-05-01&to=2026-05-31",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 200
    coach_ids = {row["coach_id"] for row in r.json()}
    assert two_gyms["a"]["coach_id"] in coach_ids
    assert two_gyms["b"]["coach_id"] not in coach_ids


def test_owner_cannot_assign_foreign_coach_to_own_class(client: TestClient, two_gyms: dict) -> None:
    """Cross-tenant payload: A's class, B's coach → 404 on the coach."""
    r = client.post(
        f"/api/v1/classes/{two_gyms['a']['class_id']}/coaches",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "coach_id": two_gyms["b"]["coach_id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "fixed",
            "pay_amount_cents": 100000,
            "weekdays": [],
        },
    )
    assert r.status_code == 404


def test_owner_cannot_assign_own_coach_to_foreign_class(client: TestClient, two_gyms: dict) -> None:
    """Cross-tenant payload: B's class, A's coach → 404 on the class."""
    r = client.post(
        f"/api/v1/classes/{two_gyms['b']['class_id']}/coaches",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "coach_id": two_gyms["a"]["coach_id"],
            "role": "ראשי",
            "is_primary": True,
            "pay_model": "fixed",
            "pay_amount_cents": 100000,
            "weekdays": [],
        },
    )
    assert r.status_code == 404


def test_owner_cannot_list_coaches_of_foreign_class(client: TestClient, two_gyms: dict) -> None:
    """A's owner hitting B's class/coaches — list returns empty rather
    than raising; this is the ''scoped list'' pattern. Verify it's empty."""
    r = client.get(
        f"/api/v1/classes/{two_gyms['b']['class_id']}/coaches",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


def test_owner_cannot_patch_foreign_class_coach_link(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/class-coaches/{two_gyms['b']['class_coach_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"pay_amount_cents": 1},
    )
    assert r.status_code == 404


def test_owner_cannot_delete_foreign_class_coach_link(client: TestClient, two_gyms: dict) -> None:
    r = client.delete(
        f"/api/v1/class-coaches/{two_gyms['b']['class_coach_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_reassign_coach_on_foreign_entry(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/attendance/{two_gyms['b']['entry_id']}/reassign-coach",
        headers=two_gyms["a"]["owner_headers"],
        json={"coach_id": two_gyms["a"]["coach_id"]},
    )
    assert r.status_code == 404


def test_owner_cannot_reassign_to_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    """A's entry, B's coach → 404 on the coach, not a silent accept."""
    r = client.post(
        f"/api/v1/attendance/{two_gyms['a']['entry_id']}/reassign-coach",
        headers=two_gyms["a"]["owner_headers"],
        json={"coach_id": two_gyms["b"]["coach_id"]},
    )
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
#  Schedule — templates, sessions, bulk action
# ══════════════════════════════════════════════════════════════════════════════


def test_owner_cannot_read_foreign_template(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/schedule/templates/{two_gyms['b']['template_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_patch_foreign_template(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/schedule/templates/{two_gyms['b']['template_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"weekdays": ["mon"]},
    )
    assert r.status_code == 404


def test_owner_cannot_deactivate_foreign_template(client: TestClient, two_gyms: dict) -> None:
    r = client.delete(
        f"/api/v1/schedule/templates/{two_gyms['b']['template_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_templates_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get("/api/v1/schedule/templates", headers=two_gyms["a"]["owner_headers"])
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert two_gyms["a"]["template_id"] in ids
    assert two_gyms["b"]["template_id"] not in ids


def test_owner_cannot_read_foreign_session(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/schedule/sessions/{two_gyms['b']['session_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_patch_foreign_session(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/schedule/sessions/{two_gyms['b']['session_id']}",
        headers=two_gyms["a"]["owner_headers"],
        json={"notes": "hijacked"},
    )
    assert r.status_code == 404


def test_owner_cannot_cancel_foreign_session(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/schedule/sessions/{two_gyms['b']['session_id']}/cancel",
        headers=two_gyms["a"]["owner_headers"],
        json={"reason": "test"},
    )
    assert r.status_code == 404


def test_sessions_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        "/api/v1/schedule/sessions?from=2026-04-01T00:00:00Z&to=2026-12-31T00:00:00Z",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    # A's seeded session_id should be present, B's should not.
    assert two_gyms["b"]["session_id"] not in ids


def test_owner_cannot_create_adhoc_session_in_foreign_class(
    client: TestClient, two_gyms: dict
) -> None:
    r = client.post(
        "/api/v1/schedule/sessions",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "class_id": two_gyms["b"]["class_id"],
            "starts_at": "2026-06-01T15:00:00Z",
            "ends_at": "2026-06-01T16:00:00Z",
            "head_coach_id": two_gyms["a"]["coach_id"],
        },
    )
    assert r.status_code == 404


def test_owner_cannot_create_adhoc_with_foreign_coach(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        "/api/v1/schedule/sessions",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "class_id": two_gyms["a"]["class_id"],
            "starts_at": "2026-06-02T15:00:00Z",
            "ends_at": "2026-06-02T16:00:00Z",
            "head_coach_id": two_gyms["b"]["coach_id"],
        },
    )
    assert r.status_code == 404


def test_owner_bulk_action_on_foreign_class(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "class_id": two_gyms["b"]["class_id"],
            "from": "2026-05-01",
            "to": "2026-05-31",
            "action": "cancel",
        },
    )
    assert r.status_code == 404


def test_owner_cannot_toggle_other_tenant_features(client: TestClient, two_gyms: dict) -> None:
    """Owner doesn't have the role for this endpoint regardless of
    tenant — gets 403, not 404. Same protection as any super_admin-only
    surface; the cross-tenant attack vector here is "owner of A
    secretly disables features for B" which the role gate already blocks."""
    r = client.patch(
        f"/api/v1/tenants/{two_gyms['b']['tenant_id']}/features",
        headers=two_gyms["a"]["owner_headers"],
        json={"schedule": False},
    )
    assert r.status_code == 403


def test_owner_bulk_swap_to_foreign_coach_blocked(client: TestClient, two_gyms: dict) -> None:
    """Substitute-pay path also enforces tenant scope: even with a
    valid pay rate in the body, the new coach has to be in the
    caller's tenant. Foreign coach → 404."""
    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=two_gyms["a"]["owner_headers"],
        json={
            "class_id": two_gyms["a"]["class_id"],
            "from": "2026-06-01",
            "to": "2026-06-07",
            "action": "swap_coach",
            "new_coach_id": two_gyms["b"]["coach_id"],
            "substitute_pay_model": "per_session",
            "substitute_pay_amount_cents": 4000,
        },
    )
    assert r.status_code == 404


# ── Leads ──────────────────────────────────────────────────────────────


def test_owner_cannot_read_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_sales_cannot_update_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.patch(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}",
        headers=two_gyms["a"]["sales_headers"],
        json={"notes": "hacked"},
    )
    assert r.status_code == 404


def test_sales_cannot_set_status_on_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}/status",
        headers=two_gyms["a"]["sales_headers"],
        json={"new_status": "contacted"},
    )
    assert r.status_code == 404


def test_sales_cannot_assign_foreign_user_to_own_lead(client: TestClient, two_gyms: dict) -> None:
    """A's sales tries to assign B's user to A's lead — assigned_to must
    be a user in caller's tenant. 404 for the foreign user (not 422),
    same posture as members."""
    # First create a lead in A.
    a_lead = client.post(
        "/api/v1/leads",
        headers=two_gyms["a"]["sales_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+972-50-555-0001"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{a_lead['id']}/assign",
        headers=two_gyms["a"]["sales_headers"],
        json={"user_id": two_gyms["b"]["staff_id"]},
    )
    assert r.status_code == 404


def test_sales_cannot_add_activity_to_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}/activities",
        headers=two_gyms["a"]["sales_headers"],
        json={"type": "note", "note": "foreign mutation"},
    )
    assert r.status_code == 404


def test_sales_cannot_list_activities_for_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.get(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}/activities",
        headers=two_gyms["a"]["sales_headers"],
    )
    assert r.status_code == 404


def test_sales_cannot_convert_foreign_lead(client: TestClient, two_gyms: dict) -> None:
    r = client.post(
        f"/api/v1/leads/{two_gyms['b']['lead_id']}/convert",
        headers=two_gyms["a"]["sales_headers"],
        json={"plan_id": two_gyms["a"]["plan_id"], "payment_method": "cash"},
    )
    assert r.status_code == 404


def test_convert_with_foreign_plan_blocked(client: TestClient, two_gyms: dict) -> None:
    """A's sales converts A's lead but tries to enroll against B's plan
    — must reject before any rows are written."""
    a_lead = client.post(
        "/api/v1/leads",
        headers=two_gyms["a"]["sales_headers"],
        json={"first_name": "A", "last_name": "B", "phone": "+972-50-555-0009"},
    ).json()
    r = client.post(
        f"/api/v1/leads/{a_lead['id']}/convert",
        headers=two_gyms["a"]["sales_headers"],
        json={"plan_id": two_gyms["b"]["plan_id"], "payment_method": "cash"},
    )
    # Cross-tenant plan surfaces as 422 — the payload itself is the
    # malformed cross-tenant link, matching the existing subscriptions
    # cross-tenant probe semantics.
    assert r.status_code == 422

    # And the lead is unchanged.
    after = client.get(
        f"/api/v1/leads/{a_lead['id']}",
        headers=two_gyms["a"]["sales_headers"],
    ).json()
    assert after["status"] == "new"


def test_leads_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    """A's owner sees ONLY A's lead in the list — never B's."""
    r = client.get("/api/v1/leads", headers=two_gyms["a"]["owner_headers"])
    assert r.status_code == 200
    ids = {ld["id"] for ld in r.json()}
    assert two_gyms["a"]["lead_id"] in ids
    assert two_gyms["b"]["lead_id"] not in ids


def test_lost_reasons_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    """B logs a lost reason. A's owner asking for autocomplete must NOT
    see B's reason."""
    # B marks its lead lost.
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        s.execute(
            text("UPDATE leads SET status = 'lost', lost_reason = 'b-only-reason' WHERE id = :l"),
            {"l": two_gyms["b"]["lead_id"]},
        )
        s.commit()
    engine.dispose()

    r = client.get(
        "/api/v1/leads/lost-reasons",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 200
    reasons = {row["reason"] for row in r.json()}
    assert "b-only-reason" not in reasons


# ── Payments ──────────────────────────────────────────────────────────


def test_staff_cannot_record_payment_for_foreign_member(client: TestClient, two_gyms: dict) -> None:
    """A's staff sets ``member_id`` to B's member — service rejects with 404."""
    r = client.post(
        "/api/v1/payments",
        headers=two_gyms["a"]["staff_headers"],
        json={
            "member_id": two_gyms["b"]["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    )
    assert r.status_code == 404


def test_staff_cannot_record_with_foreign_subscription(client: TestClient, two_gyms: dict) -> None:
    """A's staff sends A's member but B's sub_id — sub-tenant check rejects."""
    r = client.post(
        "/api/v1/payments",
        headers=two_gyms["a"]["staff_headers"],
        json={
            "member_id": two_gyms["a"]["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
            "subscription_id": two_gyms["b"]["sub_id"],
        },
    )
    assert r.status_code == 404


def test_owner_cannot_read_foreign_payment(client: TestClient, two_gyms: dict) -> None:
    """B records a payment, A's owner tries to fetch it → 404."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        b_payment_id = s.execute(
            text(
                "INSERT INTO payments "
                "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                "VALUES (:t, :m, 1000, 'ILS', 'cash', :d) RETURNING id"
            ),
            {"t": two_gyms["b"]["tenant_id"], "m": two_gyms["b"]["member_id"], "d": date.today()},
        ).scalar_one()
        s.commit()
    engine.dispose()

    r = client.get(
        f"/api/v1/payments/{b_payment_id}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404


def test_owner_cannot_refund_foreign_payment(client: TestClient, two_gyms: dict) -> None:
    """A's owner tries to refund B's payment — 404 for the foreign id."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        b_payment_id = s.execute(
            text(
                "INSERT INTO payments "
                "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                "VALUES (:t, :m, 1000, 'ILS', 'cash', :d) RETURNING id"
            ),
            {"t": two_gyms["b"]["tenant_id"], "m": two_gyms["b"]["member_id"], "d": date.today()},
        ).scalar_one()
        s.commit()
    engine.dispose()

    r = client.post(
        f"/api/v1/payments/{b_payment_id}/refund",
        headers=two_gyms["a"]["owner_headers"],
        json={},
    )
    assert r.status_code == 404


def test_payments_list_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    """A's owner sees only A's payments — never B's."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        for tenant_key in ("a", "b"):
            s.execute(
                text(
                    "INSERT INTO payments "
                    "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                    "VALUES (:t, :m, 1000, 'ILS', 'cash', :d)"
                ),
                {
                    "t": two_gyms[tenant_key]["tenant_id"],
                    "m": two_gyms[tenant_key]["member_id"],
                    "d": date.today(),
                },
            )
        s.commit()
    engine.dispose()

    r = client.get("/api/v1/payments", headers=two_gyms["a"]["owner_headers"])
    assert r.status_code == 200
    rows = r.json()
    assert all(p["tenant_id"] == two_gyms["a"]["tenant_id"] for p in rows)


def test_dashboard_revenue_scopes_to_caller_tenant(client: TestClient, two_gyms: dict) -> None:
    """B has 50000 in revenue this month; A's owner asks for /revenue
    and sees ONLY their own (which is 0)."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        s.execute(
            text(
                "INSERT INTO payments "
                "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                "VALUES (:t, :m, 50000, 'ILS', 'cash', :d)"
            ),
            {
                "t": two_gyms["b"]["tenant_id"],
                "m": two_gyms["b"]["member_id"],
                "d": date.today(),
            },
        )
        s.commit()
    engine.dispose()

    r = client.get("/api/v1/dashboard/revenue", headers=two_gyms["a"]["owner_headers"])
    assert r.status_code == 200
    assert r.json()["this_month"]["cents"] == 0


def test_member_payments_endpoint_rejects_foreign_member(
    client: TestClient, two_gyms: dict
) -> None:
    r = client.get(
        f"/api/v1/members/{two_gyms['b']['member_id']}/payments",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code == 404
