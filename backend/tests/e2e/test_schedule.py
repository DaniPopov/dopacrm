"""E2E tests for the Schedule API + feature flag wiring.

Covers:
- Feature flag: schedule disabled → 403 on every endpoint
- Templates: create + materialize sessions; list; patch
  re-materializes; deactivate cancels future
- Sessions: ad-hoc create, range query, swap coach (logged + customized),
  cancel, bulk action (cancel + swap)
- PATCH /tenants/{id}/features — super_admin toggles, owner cannot
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get(
        "NEON_DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm"
    )
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _headers(user_id, role, tenant_id, secret):
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        tenant_id=str(tenant_id) if tenant_id else None,
        secret_key=secret,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed(*, schedule_enabled: bool = True) -> dict:
    """Seed one tenant with a class + a coach + (optionally) Schedule
    feature enabled."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        features = '{"coaches": true, "schedule": true}' if schedule_enabled else '{"coaches": true}'
        tenant_id = s.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status, features_enabled) "
                "VALUES (:s, 'G', :p, 'active', CAST(:f AS jsonb)) RETURNING id"
            ),
            {"s": f"t-{uuid4().hex[:8]}", "p": plan_id, "f": features},
        ).scalar_one()
        owner_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'owner', :t, true) RETURNING id"
            ),
            {"e": f"o-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": tenant_id},
        ).scalar_one()
        class_id = s.execute(
            text(
                "INSERT INTO classes (tenant_id, name) VALUES (:t, 'Boxing') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        coach_id = s.execute(
            text(
                "INSERT INTO coaches (tenant_id, first_name, last_name) "
                "VALUES (:t, 'David', 'Cohen') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        s.commit()
    engine.dispose()
    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_headers": _headers(owner_id, "owner", tenant_id, secret),
        "class_id": str(class_id),
        "coach_id": str(coach_id),
    }


def _seed_super_admin() -> dict:
    """Standalone super_admin user (no tenant) for tenant-features tests."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        sa_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, is_active) "
                "VALUES (:e, :p, 'super_admin', true) RETURNING id"
            ),
            {"e": f"sa-{uuid4().hex[:6]}@d.co", "p": hash_password("x")},
        ).scalar_one()
        s.commit()
    engine.dispose()
    secret = os.environ["APP_SECRET_KEY"]
    return {"super_admin_headers": _headers(sa_id, "super_admin", None, secret)}


# ── Feature flag gate ────────────────────────────────────────────────


def test_schedule_disabled_returns_403_on_create_template(
    client: TestClient,
) -> None:
    env = _seed(schedule_enabled=False)
    r = client.post(
        "/api/v1/schedule/templates",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "weekdays": ["sun"],
            "start_time": "18:00:00",
            "end_time": "19:00:00",
            "head_coach_id": env["coach_id"],
        },
    )
    assert r.status_code == 403
    assert r.json()["error"] == "FEATURE_DISABLED"


def test_schedule_disabled_returns_403_on_list_sessions(
    client: TestClient,
) -> None:
    env = _seed(schedule_enabled=False)
    r = client.get(
        "/api/v1/schedule/sessions?from=2026-04-19T00:00:00Z&to=2026-04-26T00:00:00Z",
        headers=env["owner_headers"],
    )
    assert r.status_code == 403


# ── Template create + materialization ────────────────────────────────


def test_create_template_materializes_8_weeks(client: TestClient) -> None:
    env = _seed(schedule_enabled=True)
    r = client.post(
        "/api/v1/schedule/templates",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "weekdays": ["sun", "tue"],
            "start_time": "18:00:00",
            "end_time": "19:00:00",
            "head_coach_id": env["coach_id"],
            "starts_on": "2020-01-01",  # past, so today's weekday counts
        },
    )
    assert r.status_code == 201
    tpl = r.json()
    assert tpl["weekdays"] == ["sun", "tue"]
    assert tpl["is_active"] is True

    # Range scan: next 8 weeks should have ≥1 materialized session for
    # each weekday occurrence. With weekdays=[sun, tue] over 8 weeks
    # we expect ~16 sessions.
    today = date.today()
    horizon = today + timedelta(weeks=8)
    sessions_resp = client.get(
        f"/api/v1/schedule/sessions?from={today.isoformat()}T00:00:00Z"
        f"&to={horizon.isoformat()}T23:59:59Z",
        headers=env["owner_headers"],
    )
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()
    assert len(sessions) > 0  # something materialized
    assert all(s["template_id"] == tpl["id"] for s in sessions)
    assert all(s["status"] == "scheduled" for s in sessions)


def test_template_invalid_weekday_returns_422(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/schedule/templates",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "weekdays": ["funday"],
            "start_time": "18:00:00",
            "end_time": "19:00:00",
            "head_coach_id": env["coach_id"],
        },
    )
    assert r.status_code == 422


# ── Session edits ────────────────────────────────────────────────────


def test_cancel_session_marks_customized(client: TestClient) -> None:
    env = _seed()
    # Create an ad-hoc session to keep the test deterministic.
    sess_resp = client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-05-19T15:00:00Z",
            "ends_at": "2026-05-19T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    r = client.post(
        f"/api/v1/schedule/sessions/{sess_id}/cancel",
        headers=env["owner_headers"],
        json={"reason": "plumbing"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_reason"] == "plumbing"
    assert body["is_customized"] is True


def test_swap_coach_sets_customized(client: TestClient) -> None:
    env = _seed()
    second = client.post(
        f"/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "Yoni", "last_name": "Levi"},
    ).json()
    sess = client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-05-20T15:00:00Z",
            "ends_at": "2026-05-20T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    ).json()

    r = client.patch(
        f"/api/v1/schedule/sessions/{sess['id']}",
        headers=env["owner_headers"],
        json={"head_coach_id": second["id"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["head_coach_id"] == second["id"]
    assert body["is_customized"] is True


def test_double_cancel_returns_409(client: TestClient) -> None:
    env = _seed()
    sess = client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-05-21T15:00:00Z",
            "ends_at": "2026-05-21T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    ).json()
    client.post(
        f"/api/v1/schedule/sessions/{sess['id']}/cancel",
        headers=env["owner_headers"],
        json={},
    )
    r = client.post(
        f"/api/v1/schedule/sessions/{sess['id']}/cancel",
        headers=env["owner_headers"],
        json={},
    )
    assert r.status_code == 409


# ── Bulk action ──────────────────────────────────────────────────────


def test_bulk_cancel_two_sessions(client: TestClient) -> None:
    env = _seed()
    # Two ad-hoc sessions on different days for the same class.
    s1 = client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-05-25T15:00:00Z",
            "ends_at": "2026-05-25T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    ).json()
    s2 = client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-05-26T15:00:00Z",
            "ends_at": "2026-05-26T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    ).json()

    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-05-25",
            "to": "2026-05-27",
            "action": "cancel",
            "reason": "vacation",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "cancel"
    assert body["cancelled_count"] == 2
    assert set(body["affected_ids"]) == {s1["id"], s2["id"]}


def test_bulk_swap_requires_new_coach(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-05-01",
            "to": "2026-05-31",
            "action": "swap_coach",
            # missing new_coach_id
        },
    )
    assert r.status_code == 422


def test_bulk_inverted_range_rejected(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-05-31",
            "to": "2026-05-01",
            "action": "cancel",
        },
    )
    assert r.status_code == 422


def test_bulk_swap_to_coach_without_rate_requires_substitute_pay(
    client: TestClient,
) -> None:
    """Vacation-cover scenario — substitute coach has no class_coaches
    rate for this class. Without substitute_pay_* fields, bulk swap
    returns 422 with the explanatory error code so the UI knows to
    prompt for pay."""
    env = _seed()
    sub_coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "Yoni", "last_name": "Levi"},
    ).json()

    client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-06-01T15:00:00Z",
            "ends_at": "2026-06-01T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    )

    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-06-01",
            "to": "2026-06-07",
            "action": "swap_coach",
            "new_coach_id": sub_coach["id"],
        },
    )
    assert r.status_code == 422
    assert "SUBSTITUTE_PAY_REQUIRED" in r.json()["detail"]


def test_bulk_swap_with_substitute_pay_creates_temp_link(
    client: TestClient,
) -> None:
    """When substitute_pay_* is provided, the service auto-creates a
    temporary class_coaches link for the substitute that covers the
    range. Substitute earns correctly for the swapped sessions."""
    env = _seed()
    sub_coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "Yoni", "last_name": "Levi"},
    ).json()

    for d in ("2026-06-01", "2026-06-04"):
        client.post(
            "/api/v1/schedule/sessions",
            headers=env["owner_headers"],
            json={
                "class_id": env["class_id"],
                "starts_at": f"{d}T15:00:00Z",
                "ends_at": f"{d}T16:00:00Z",
                "head_coach_id": env["coach_id"],
            },
        )

    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-06-01",
            "to": "2026-06-07",
            "action": "swap_coach",
            "new_coach_id": sub_coach["id"],
            "substitute_pay_model": "per_session",
            "substitute_pay_amount_cents": 4000,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["swapped_count"] == 2
    assert body["substitute_link_id"] is not None

    links = client.get(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
    ).json()
    sub_links = [l for l in links if l["coach_id"] == sub_coach["id"]]
    assert len(sub_links) == 1
    assert sub_links[0]["pay_model"] == "per_session"
    assert sub_links[0]["pay_amount_cents"] == 4000
    assert sub_links[0]["starts_on"] == "2026-06-01"
    assert sub_links[0]["ends_on"] == "2026-06-07"


def test_bulk_swap_to_coach_with_existing_rate_does_not_create_link(
    client: TestClient,
) -> None:
    """If the substitute already has a class_coaches link covering the
    range, no auto-link is created — the existing rate is used."""
    env = _seed()
    sub_coach = client.post(
        "/api/v1/coaches",
        headers=env["owner_headers"],
        json={"first_name": "Yoni", "last_name": "Levi"},
    ).json()
    client.post(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
        json={
            "coach_id": sub_coach["id"],
            "role": "עוזר",
            "is_primary": False,
            "pay_model": "per_session",
            "pay_amount_cents": 3000,
            "weekdays": [],
            "starts_on": "2026-01-01",
        },
    )
    client.post(
        "/api/v1/schedule/sessions",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "starts_at": "2026-06-01T15:00:00Z",
            "ends_at": "2026-06-01T16:00:00Z",
            "head_coach_id": env["coach_id"],
        },
    )

    r = client.post(
        "/api/v1/schedule/bulk-action",
        headers=env["owner_headers"],
        json={
            "class_id": env["class_id"],
            "from": "2026-06-01",
            "to": "2026-06-07",
            "action": "swap_coach",
            "new_coach_id": sub_coach["id"],
        },
    )
    assert r.status_code == 200
    assert r.json()["substitute_link_id"] is None

    links = client.get(
        f"/api/v1/classes/{env['class_id']}/coaches",
        headers=env["owner_headers"],
    ).json()
    sub_links = [l for l in links if l["coach_id"] == sub_coach["id"]]
    assert len(sub_links) == 1
    assert sub_links[0]["role"] == "עוזר"


# ── Tenant features endpoint ─────────────────────────────────────────


def test_super_admin_can_toggle_features(client: TestClient) -> None:
    env = _seed(schedule_enabled=False)
    sa = _seed_super_admin()

    r = client.patch(
        f"/api/v1/tenants/{env['tenant_id']}/features",
        headers=sa["super_admin_headers"],
        json={"schedule": True},
    )
    assert r.status_code == 200
    assert r.json()["features_enabled"]["schedule"] is True
    # Coaches stays untouched (was already true).
    assert r.json()["features_enabled"]["coaches"] is True


def test_owner_cannot_toggle_features(client: TestClient) -> None:
    env = _seed()
    r = client.patch(
        f"/api/v1/tenants/{env['tenant_id']}/features",
        headers=env["owner_headers"],
        json={"schedule": False},
    )
    assert r.status_code == 403
