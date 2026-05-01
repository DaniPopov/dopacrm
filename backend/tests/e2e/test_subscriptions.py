"""E2E tests for Subscriptions endpoints + security + state machine.

Covers the public HTTP contract — happy paths, permission gates, tenant
scoping, state-machine 409s, price-lock invariant, member.status sync,
event-log writes, renew-from-expired, and the plan-change flow.
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
    url = os.environ.get("DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
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
    """Seed a tenant + owner/staff/sales users + one member + two plans."""
    engine = create_engine(_sync_url())
    with Session(engine) as session:
        saas_plan_id = session.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = session.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status) "
                "VALUES (:s, :n, :p, 'active') RETURNING id"
            ),
            {"s": f"gym-{uuid4().hex[:8]}", "n": "Gym", "p": saas_plan_id},
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
        sales_id = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'sales', :t, true) RETURNING id"
            ),
            {"e": f"sales-{uuid4().hex[:6]}@g.co", "p": hash_password("Pass1!cc"), "t": tenant_id},
        ).scalar_one()
        member_id = session.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'Dana', 'Cohen', :ph) RETURNING id"
            ),
            {"t": tenant_id, "ph": f"050{uuid4().hex[:7]}"},
        ).scalar_one()
        silver_id = session.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period) "
                "VALUES (:t, 'Silver', 'recurring', 25000, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        gold_id = session.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period) "
                "VALUES (:t, 'Gold', 'recurring', 45000, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "member_id": str(member_id),
        "silver_id": str(silver_id),
        "gold_id": str(gold_id),
        "owner_headers": _auth_headers(owner_id, "owner", tenant_id, secret),
        "staff_headers": _auth_headers(staff_id, "staff", tenant_id, secret),
        "sales_headers": _auth_headers(sales_id, "sales", tenant_id, secret),
    }


def _create_sub(client: TestClient, headers: dict, **overrides) -> dict:
    body = {**overrides}
    resp = client.post("/api/v1/subscriptions", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Create + permissions ─────────────────────────────────────────────────────


def test_staff_can_create_subscription(client: TestClient, gym_setup: dict) -> None:
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    assert data["status"] == "active"
    assert data["member_id"] == gym_setup["member_id"]
    assert data["plan_id"] == gym_setup["silver_id"]
    # Price locked from the plan
    assert data["price_cents"] == 25000
    assert data["currency"] == "ILS"


def test_owner_can_create_subscription(client: TestClient, gym_setup: dict) -> None:
    data = _create_sub(
        client,
        gym_setup["owner_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    assert data["status"] == "active"


def test_sales_cannot_create_subscription(client: TestClient, gym_setup: dict) -> None:
    """Sales is read-only for subs (they read the catalog but don't enroll)."""
    r = client.post(
        "/api/v1/subscriptions",
        headers=gym_setup["sales_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "plan_id": gym_setup["silver_id"],
        },
    )
    assert r.status_code == 403


def test_super_admin_cannot_create_subscription(
    client: TestClient, auth_headers: dict, gym_setup: dict
) -> None:
    """Platform-level role — blocked from gym-scoped commercial ops."""
    r = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "member_id": gym_setup["member_id"],
            "plan_id": gym_setup["silver_id"],
        },
    )
    assert r.status_code == 403


def test_second_live_sub_for_same_member_is_rejected(client: TestClient, gym_setup: dict) -> None:
    _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.post(
        "/api/v1/subscriptions",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "plan_id": gym_setup["gold_id"],
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "MEMBER_HAS_ACTIVE_SUBSCRIPTION"


def test_cannot_use_plan_from_another_tenant(client: TestClient, gym_setup: dict) -> None:
    """Seed a second tenant + plan, try to enroll gym_setup's member into it."""
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
        other_plan_id = session.execute(
            text(
                "INSERT INTO membership_plans (tenant_id, name, type, price_cents, "
                "currency, billing_period) VALUES "
                "(:t, 'Foreign', 'recurring', 1, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": other_tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()

    r = client.post(
        "/api/v1/subscriptions",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "plan_id": str(other_plan_id),
        },
    )
    assert r.status_code == 422
    assert r.json()["error"] == "SUBSCRIPTION_PLAN_TENANT_MISMATCH"


def test_create_with_explicit_expires_at_cash_flow(client: TestClient, gym_setup: dict) -> None:
    """Cash-payment flow: staff sets expires_at = today + 30 days."""
    due = (date.today() + timedelta(days=30)).isoformat()
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        expires_at=due,
    )
    assert data["expires_at"] == due


def test_create_without_expires_at_for_recurring_plan_means_card_auto(
    client: TestClient, gym_setup: dict
) -> None:
    """Card-auto flow: recurring plan + no expires_at → runs until cancelled."""
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    assert data["expires_at"] is None


# ── Freeze / Unfreeze ────────────────────────────────────────────────────────


def test_freeze_then_unfreeze_happy_path(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "frozen"

    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/unfreeze",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_freeze_with_frozen_until_records_the_date(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    until = (date.today() + timedelta(days=14)).isoformat()
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={"frozen_until": until},
    )
    assert r.status_code == 200
    assert r.json()["frozen_until"] == until


def test_cannot_freeze_an_already_frozen_sub(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={},
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "SUBSCRIPTION_INVALID_TRANSITION"


# ── Renew ────────────────────────────────────────────────────────────────────


def test_renew_extends_expires_at_by_billing_period_default(
    client: TestClient, gym_setup: dict
) -> None:
    """Default extension for monthly = +30 days from the current expires_at."""
    original_expiry = date.today() + timedelta(days=20)
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        expires_at=original_expiry.isoformat(),
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/renew",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "active"
    # Should be roughly original_expiry + 30d (the service takes max(today, expiry))
    expected = (original_expiry + timedelta(days=30)).isoformat()
    assert data["expires_at"] == expected


def test_renew_accepts_explicit_new_expires_at(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        expires_at=(date.today() + timedelta(days=10)).isoformat(),
    )
    override = (date.today() + timedelta(days=60)).isoformat()
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/renew",
        headers=gym_setup["staff_headers"],
        json={"new_expires_at": override},
    )
    assert r.status_code == 200
    assert r.json()["expires_at"] == override


# ── Change plan ──────────────────────────────────────────────────────────────


def test_change_plan_creates_new_sub_marks_old_replaced_with_fresh_price(
    client: TestClient, gym_setup: dict
) -> None:
    """Silver → Gold. Old sub becomes 'replaced' + links forward; new sub
    has Gold's price locked (not Silver's)."""
    old = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )

    r = client.post(
        f"/api/v1/subscriptions/{old['id']}/change-plan",
        headers=gym_setup["staff_headers"],
        json={"new_plan_id": gym_setup["gold_id"]},
    )
    assert r.status_code == 200, r.text
    new_sub = r.json()
    assert new_sub["status"] == "active"
    assert new_sub["plan_id"] == gym_setup["gold_id"]
    assert new_sub["price_cents"] == 45000  # Gold's price, not Silver's
    assert new_sub["id"] != old["id"]

    # Old sub became replaced and points forward
    r2 = client.get(
        f"/api/v1/subscriptions/{old['id']}",
        headers=gym_setup["staff_headers"],
    )
    assert r2.status_code == 200
    refreshed_old = r2.json()
    assert refreshed_old["status"] == "replaced"
    assert refreshed_old["replaced_by_id"] == new_sub["id"]


def test_change_plan_rejects_same_plan(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/change-plan",
        headers=gym_setup["staff_headers"],
        json={"new_plan_id": gym_setup["silver_id"]},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "SUBSCRIPTION_SAME_PLAN"


# ── Cancel ───────────────────────────────────────────────────────────────────


def test_cancel_is_hard_terminal_and_records_reason(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/cancel",
        headers=gym_setup["staff_headers"],
        json={"reason": "too_expensive", "detail": "Switching gyms"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "cancelled"
    assert data["cancellation_reason"] == "too_expensive"

    # Second cancel rejected — hard-terminal
    r2 = client.post(
        f"/api/v1/subscriptions/{sub['id']}/cancel",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r2.status_code == 409


def test_cancelled_cannot_renew(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/cancel",
        headers=gym_setup["staff_headers"],
        json={},
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/renew",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert r.status_code == 409


# ── Reads ────────────────────────────────────────────────────────────────────


def test_list_subscriptions_scoped_to_tenant(client: TestClient, gym_setup: dict) -> None:
    _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.get("/api/v1/subscriptions", headers=gym_setup["staff_headers"])
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_filter_by_member_id(client: TestClient, gym_setup: dict) -> None:
    _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    r = client.get(
        f"/api/v1/subscriptions?member_id={gym_setup['member_id']}",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_filter_by_expires_within_days(client: TestClient, gym_setup: dict) -> None:
    """The 'about to expire this week' dashboard query."""
    _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        expires_at=(date.today() + timedelta(days=3)).isoformat(),
    )
    r = client.get(
        "/api/v1/subscriptions?expires_within_days=7",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 1-day window → excludes the 3-day-out sub
    r2 = client.get(
        "/api/v1/subscriptions?expires_within_days=1",
        headers=gym_setup["staff_headers"],
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 0


def test_cross_tenant_get_returns_404(client: TestClient, gym_setup: dict) -> None:
    """Other-tenant staff sees 404 (not 403) — no existence leak."""
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    # Spin up a second tenant with its own staff
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
            {"e": f"s-{uuid4().hex[:6]}@g.co", "p": hash_password("x"), "t": other_tenant_id},
        ).scalar_one()
        session.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    other_headers = _auth_headers(staff_id, "staff", other_tenant_id, secret)
    r = client.get(f"/api/v1/subscriptions/{sub['id']}", headers=other_headers)
    assert r.status_code == 404


# ── Events / timeline ────────────────────────────────────────────────────────


def test_events_endpoint_returns_full_timeline(client: TestClient, gym_setup: dict) -> None:
    """Lifecycle: create → freeze → unfreeze → cancel. Timeline should have
    all four events newest first."""
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={},
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/unfreeze",
        headers=gym_setup["staff_headers"],
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/cancel",
        headers=gym_setup["staff_headers"],
        json={"reason": "moved_away"},
    )

    r = client.get(
        f"/api/v1/subscriptions/{sub['id']}/events",
        headers=gym_setup["staff_headers"],
    )
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 4
    types = {e["event_type"] for e in events}
    assert types == {"created", "frozen", "unfrozen", "cancelled"}

    # Cancelled event carries the reason
    cancelled_event = next(e for e in events if e["event_type"] == "cancelled")
    assert cancelled_event["event_data"]["reason"] == "moved_away"


# ── Member.status sync ───────────────────────────────────────────────────────


def _get_member_status(member_id: str) -> str:
    engine = create_engine(_sync_url())
    try:
        with Session(engine) as session:
            return session.execute(
                text("SELECT status FROM members WHERE id = :id"),
                {"id": member_id},
            ).scalar_one()
    finally:
        engine.dispose()


def test_member_status_syncs_on_freeze_and_unfreeze(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    assert _get_member_status(gym_setup["member_id"]) == "active"

    client.post(
        f"/api/v1/subscriptions/{sub['id']}/freeze",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert _get_member_status(gym_setup["member_id"]) == "frozen"

    client.post(
        f"/api/v1/subscriptions/{sub['id']}/unfreeze",
        headers=gym_setup["staff_headers"],
    )
    assert _get_member_status(gym_setup["member_id"]) == "active"


# ── Payment method ──────────────────────────────────────────────────────────


def test_create_defaults_payment_method_to_cash(client: TestClient, gym_setup: dict) -> None:
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    assert data["payment_method"] == "cash"
    assert data["payment_method_detail"] is None


def test_create_with_explicit_payment_method_and_detail(
    client: TestClient, gym_setup: dict
) -> None:
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        payment_method="credit_card",
        payment_method_detail="Visa 1234",
    )
    assert data["payment_method"] == "credit_card"
    assert data["payment_method_detail"] == "Visa 1234"


def test_create_with_other_method_accepts_free_text(client: TestClient, gym_setup: dict) -> None:
    data = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        payment_method="other",
        payment_method_detail="bank transfer, ref 9876",
    )
    assert data["payment_method"] == "other"
    assert data["payment_method_detail"] == "bank transfer, ref 9876"


def test_create_rejects_unknown_payment_method(client: TestClient, gym_setup: dict) -> None:
    r = client.post(
        "/api/v1/subscriptions",
        headers=gym_setup["staff_headers"],
        json={
            "member_id": gym_setup["member_id"],
            "plan_id": gym_setup["silver_id"],
            "payment_method": "bitcoin",
        },
    )
    assert r.status_code == 422


def test_renew_can_switch_payment_method(client: TestClient, gym_setup: dict) -> None:
    """The common flow: member on cash moves to standing order at renewal."""
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        payment_method="cash",
        expires_at=(date.today() + timedelta(days=5)).isoformat(),
    )
    r = client.post(
        f"/api/v1/subscriptions/{sub['id']}/renew",
        headers=gym_setup["staff_headers"],
        json={"new_payment_method": "standing_order"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["payment_method"] == "standing_order"

    # Event log records the change
    events = client.get(
        f"/api/v1/subscriptions/{sub['id']}/events",
        headers=gym_setup["staff_headers"],
    ).json()
    renew_event = next(e for e in events if e["event_type"] == "renewed")
    assert renew_event["event_data"]["previous_payment_method"] == "cash"
    assert renew_event["event_data"]["new_payment_method"] == "standing_order"


def test_change_plan_carries_over_payment_method(client: TestClient, gym_setup: dict) -> None:
    """Plan change is a catalog change, not a payment-style change —
    new sub inherits the old sub's payment method."""
    old = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
        payment_method="credit_card",
        payment_method_detail="Mastercard 5678",
    )
    r = client.post(
        f"/api/v1/subscriptions/{old['id']}/change-plan",
        headers=gym_setup["staff_headers"],
        json={"new_plan_id": gym_setup["gold_id"]},
    )
    assert r.status_code == 200
    new_sub = r.json()
    assert new_sub["payment_method"] == "credit_card"
    assert new_sub["payment_method_detail"] == "Mastercard 5678"


# ── Member.status sync (continues below) ────────────────────────────────────


def test_member_status_syncs_on_cancel(client: TestClient, gym_setup: dict) -> None:
    sub = _create_sub(
        client,
        gym_setup["staff_headers"],
        member_id=gym_setup["member_id"],
        plan_id=gym_setup["silver_id"],
    )
    client.post(
        f"/api/v1/subscriptions/{sub['id']}/cancel",
        headers=gym_setup["staff_headers"],
        json={},
    )
    assert _get_member_status(gym_setup["member_id"]) == "cancelled"
