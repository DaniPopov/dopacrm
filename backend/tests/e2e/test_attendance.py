"""E2E tests for the Attendance endpoints.

Covers the HTTP contract:
- Role gates (staff/owner pass, sales/super_admin blocked)
- Quota-check happy path + not-covered + quota-exceeded results
- Record happy path + 409 when no sub + override flows
- Undo within 24h + 409 past the window + 409 double-undo
- Cross-tenant 404
- List filters for owner audit
- Summary endpoint returns one entry per entitlement
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get(
        "NEON_DATABASE_URL",
        "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm",
    )
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _auth_headers(user_id, role: str, tenant_id, secret: str) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id) if tenant_id else None,
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def gym_setup() -> dict:
    """Seed: tenant + owner/staff/sales users + member + yoga class + 3/week plan + active sub."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        saas_plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, 'Gym', :p, 'active') RETURNING id"
            ),
            {"s": f"g-{uuid4().hex[:8]}", "p": saas_plan_id},
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
                "VALUES (:t, 'Dana', 'Cohen', :ph) RETURNING id"
            ),
            {"t": tenant_id, "ph": f"05{uuid4().hex[:8]}"},
        ).scalar_one()
        yoga_id = session.execute(
            text("INSERT INTO classes (tenant_id, name) VALUES (:t, 'Yoga') RETURNING id"),
            {"t": tenant_id},
        ).scalar_one()
        spin_id = session.execute(
            text("INSERT INTO classes (tenant_id, name) VALUES (:t, 'Spinning') RETURNING id"),
            {"t": tenant_id},
        ).scalar_one()
        plan_id = session.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period) "
                "VALUES (:t, 'Yoga 3/week', 'recurring', 25000, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        # Entitlement: 3 yoga per week
        session.execute(
            text(
                "INSERT INTO plan_entitlements (plan_id, class_id, quantity, reset_period) "
                "VALUES (:p, :c, 3, 'weekly')"
            ),
            {"p": plan_id, "c": yoga_id},
        )
        sub_id = session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at) VALUES "
                "(:t, :m, :p, 'active', 25000, 'ILS', :s, NULL) RETURNING id"
            ),
            {
                "t": tenant_id,
                "m": member_id,
                "p": plan_id,
                "s": date.today(),
            },
        ).scalar_one()
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "member_id": str(member_id),
        "yoga_id": str(yoga_id),
        "spin_id": str(spin_id),
        "plan_id": str(plan_id),
        "sub_id": str(sub_id),
        "owner_headers": _auth_headers(owner_id, "owner", tenant_id, secret),
        "staff_headers": _auth_headers(staff_id, "staff", tenant_id, secret),
        "sales_headers": _auth_headers(sales_id, "sales", tenant_id, secret),
    }


def _record(client: TestClient, headers: dict, **overrides) -> dict:
    body = {**overrides}
    r = client.post("/api/v1/attendance", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── Quota check ──────────────────────────────────────────────────────────────


def test_quota_check_for_covered_class_returns_remaining(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.get(
        f"/api/v1/attendance/quota-check?member_id={gym_setup['member_id']}"
        f"&class_id={gym_setup['yoga_id']}",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["allowed"] is True
    assert data["remaining"] == 3
    assert data["quantity"] == 3
    assert data["used"] == 0


def test_quota_check_for_not_covered_class_is_disallowed(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.get(
        f"/api/v1/attendance/quota-check?member_id={gym_setup['member_id']}"
        f"&class_id={gym_setup['spin_id']}",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False
    assert r.json()["reason"] == "not_covered"


def test_quota_check_returns_409_when_member_has_no_active_sub(
    client: TestClient, gym_setup: dict
) -> None:
    """Seed a second member with no sub — quota-check should 409."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        member_id = session.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'A', 'B', :ph) RETURNING id"
            ),
            {"t": gym_setup["tenant_id"], "ph": f"05{uuid4().hex[:8]}"},
        ).scalar_one()
        session.commit()
    engine.dispose()
    r = client.get(
        f"/api/v1/attendance/quota-check?member_id={member_id}&class_id={gym_setup['yoga_id']}",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 409
    assert r.json()["error"] == "MEMBER_NO_ACTIVE_SUBSCRIPTION"


# ── Record ──────────────────────────────────────────────────────────────────


def test_staff_can_record_covered_entry(client: TestClient, gym_setup: dict) -> None:
    data = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    assert data["member_id"] == gym_setup["member_id"]
    assert data["class_id"] == gym_setup["yoga_id"]
    assert data["subscription_id"] == gym_setup["sub_id"]
    assert data["override"] is False
    assert data["undone_at"] is None


def test_sales_cannot_record_entry(client: TestClient, gym_setup: dict) -> None:
    r = client.post(
        "/api/v1/attendance",
        headers=gym_setup["sales_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["yoga_id"],
        },
    )
    assert r.status_code == 403


def test_record_returns_409_for_not_covered_without_override(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["spin_id"],
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "ATTENDANCE_CLASS_NOT_COVERED"


def test_record_not_covered_with_override_succeeds_and_flags(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["spin_id"],
            "override": True,
            "override_reason": "birthday class",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["override"] is True
    assert data["override_kind"] == "not_covered"
    assert data["override_reason"] == "birthday class"


def test_record_returns_409_when_quota_exceeded(client: TestClient, gym_setup: dict) -> None:
    """Use up the 3-per-week quota then try a 4th."""
    for _ in range(3):
        _record(
            client,
            gym_setup["staff_headers"],
            member_id=gym_setup["member_id"],
            class_id=gym_setup["yoga_id"],
        )
    r = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["yoga_id"],
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "ATTENDANCE_QUOTA_EXCEEDED"


def test_record_quota_exceeded_with_override_flags_row(client: TestClient, gym_setup: dict) -> None:
    for _ in range(3):
        _record(
            client,
            gym_setup["staff_headers"],
            member_id=gym_setup["member_id"],
            class_id=gym_setup["yoga_id"],
        )
    r = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["yoga_id"],
            "override": True,
        },
    )
    assert r.status_code == 201
    assert r.json()["override_kind"] == "quota_exceeded"


# ── Undo ────────────────────────────────────────────────────────────────────


def test_staff_can_undo_within_window(client: TestClient, gym_setup: dict) -> None:
    entry = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    r = client.post(
        f"/api/v1/attendance/{entry['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={"reason": "wrong member"},
    )
    assert r.status_code == 200
    assert r.json()["undone_at"] is not None
    assert r.json()["undone_reason"] == "wrong member"


def test_double_undo_is_rejected(client: TestClient, gym_setup: dict) -> None:
    entry = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    r1 = client.post(
        f"/api/v1/attendance/{entry['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/attendance/{entry['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "ATTENDANCE_ALREADY_UNDONE"


def test_undo_past_window_rejected(client: TestClient, gym_setup: dict) -> None:
    """Backdate an entry via raw SQL to 25 hours ago, then try to undo."""
    entry = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    twenty_five_hours_ago = datetime.now(UTC) - timedelta(hours=25)
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        session.execute(
            text("UPDATE class_entries SET entered_at = :t WHERE id = :id"),
            {"t": twenty_five_hours_ago, "id": entry["id"]},
        )
        session.commit()
    engine.dispose()

    r = client.post(
        f"/api/v1/attendance/{entry['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "ATTENDANCE_UNDO_WINDOW_EXPIRED"


def test_undone_entry_frees_quota(client: TestClient, gym_setup: dict) -> None:
    """Hit quota, undo one, should be able to record again."""
    entries = []
    for _ in range(3):
        entries.append(
            _record(
                client,
                gym_setup["staff_headers"],
                member_id=gym_setup["member_id"],
                class_id=gym_setup["yoga_id"],
            )
        )

    # At quota — 4th record would 409
    bad = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["yoga_id"],
        },
    )
    assert bad.status_code == 409

    # Undo one
    undo_r = client.post(
        f"/api/v1/attendance/{entries[0]['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert undo_r.status_code == 200

    # Now a record should work
    ok = client.post(
        "/api/v1/attendance",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "class_id": gym_setup["yoga_id"],
        },
    )
    assert ok.status_code == 201


# ── Cross-tenant isolation ─────────────────────────────────────────────────


def test_other_tenant_staff_cannot_undo_our_entry(client: TestClient, gym_setup: dict) -> None:
    entry = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    # Seed a second tenant's staff
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        saas_plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        other_tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, 'Other', :p, 'active') RETURNING id"
            ),
            {"s": f"o-{uuid4().hex[:8]}", "p": saas_plan_id},
        ).scalar_one()
        staff_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'staff', :t, true) RETURNING id"
            ),
            {"e": f"x-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": other_tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()
    secret = os.environ["APP_SECRET_KEY"]
    other_headers = _auth_headers(staff_id, "staff", other_tenant_id, secret)

    r = client.post(
        f"/api/v1/attendance/{entry['id']}/undo",
        headers=other_headers,
        json={},
    )
    assert r.status_code == 404  # no existence leak


# ── Summary endpoint ──────────────────────────────────────────────────────


def test_member_summary_returns_one_row_per_entitlement(
    client: TestClient, gym_setup: dict
) -> None:
    r = client.get(
        f"/api/v1/attendance/members/{gym_setup['member_id']}/summary",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    summaries = r.json()
    assert len(summaries) == 1
    assert summaries[0]["quantity"] == 3
    assert summaries[0]["used"] == 0
    assert summaries[0]["reset_period"] == "weekly"


def test_member_summary_empty_when_no_live_sub(client: TestClient, gym_setup: dict) -> None:
    # Seed a fresh member with no sub
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        member_id = session.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'X', 'Y', :ph) RETURNING id"
            ),
            {"t": gym_setup["tenant_id"], "ph": f"05{uuid4().hex[:8]}"},
        ).scalar_one()
        session.commit()
    engine.dispose()
    r = client.get(
        f"/api/v1/attendance/members/{member_id}/summary",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    assert r.json() == []


# ── List filters (owner audit) ─────────────────────────────────────────────


def test_list_undone_only_for_owner_audit(client: TestClient, gym_setup: dict) -> None:
    """Owner's 'mistakes this week' view."""
    e1 = _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    client.post(
        f"/api/v1/attendance/{e1['id']}/undo",
        headers=gym_setup["staff_headers"],
        json={},
    )

    r = client.get(
        "/api/v1/attendance?undone_only=true",
        headers=gym_setup["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == e1["id"]


def test_list_override_only_for_owner_audit(client: TestClient, gym_setup: dict) -> None:
    _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["yoga_id"],
    )
    _record(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        class_id=gym_setup["spin_id"],
        override=True,
        override_reason="birthday",
    )
    r = client.get(
        "/api/v1/attendance?override_only=true",
        headers=gym_setup["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["override"] is True
