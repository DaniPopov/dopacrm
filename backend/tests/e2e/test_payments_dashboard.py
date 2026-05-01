"""E2E tests for ``GET /api/v1/dashboard/revenue``.

Covers the aggregations the dashboard widgets depend on:
- Zero state (no payments) — every bucket is 0, MoM% is None
- This-month + last-month + MoM% computation
- by_plan grouping (and drop-in exclusion from by_plan)
- by_method grouping
- Refunds subtract from totals
- ARPM = this_month / count_distinct_paying_members
- Currency snapshot from tenant
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
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
    """Tenant + owner + staff + 2 members + 2 plans + 2 subs (one per plan)."""
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        plan_id = s.execute(
            text("SELECT id FROM saas_plans WHERE code = 'default' LIMIT 1")
        ).scalar_one()
        tenant_id = s.execute(
            text(
                "INSERT INTO tenants (slug, name, saas_plan_id, status, currency) "
                "VALUES (:s, 'G', :p, 'active', 'ILS') RETURNING id"
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

        members: list[str] = []
        for i in range(2):
            m = s.execute(
                text(
                    "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                    "VALUES (:t, 'M', :ln, :ph) RETURNING id"
                ),
                {"t": tenant_id, "ln": f"L{i}", "ph": f"+972-{uuid4().hex[:9]}"},
            ).scalar_one()
            members.append(str(m))

        monthly = s.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period, is_active) "
                "VALUES (:t, 'Monthly', 'recurring', 25000, 'ILS', 'monthly', true) "
                "RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        quarterly = s.execute(
            text(
                "INSERT INTO membership_plans "
                "(tenant_id, name, type, price_cents, currency, billing_period, is_active) "
                "VALUES (:t, 'Quarterly', 'recurring', 70000, 'ILS', 'quarterly', true) "
                "RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()

        s_monthly = s.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, started_at) "
                "VALUES (:t, :m, :p, 'active', 25000, 'ILS', :s) RETURNING id"
            ),
            {"t": tenant_id, "m": members[0], "p": monthly, "s": date.today()},
        ).scalar_one()
        s_quarterly = s.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, started_at) "
                "VALUES (:t, :m, :p, 'active', 70000, 'ILS', :s) RETURNING id"
            ),
            {"t": tenant_id, "m": members[1], "p": quarterly, "s": date.today()},
        ).scalar_one()

        s.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_headers": _headers(owner_id, "owner", tenant_id, secret),
        "staff_headers": _headers(staff_id, "staff", tenant_id, secret),
        "member_ids": members,
        "monthly_plan_id": str(monthly),
        "quarterly_plan_id": str(quarterly),
        "s_monthly_id": str(s_monthly),
        "s_quarterly_id": str(s_quarterly),
    }


def test_zero_state_when_no_payments(client: TestClient) -> None:
    env = _seed()
    r = client.get("/api/v1/dashboard/revenue", headers=env["owner_headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "ILS"
    assert body["this_month"]["cents"] == 0
    assert body["last_month"]["cents"] == 0
    assert body["mom_pct"] is None  # zero denominator
    assert body["by_plan"] == []
    assert body["by_method"] == {}
    assert body["arpm_cents"] == 0


def test_summary_aggregates_this_month(client: TestClient) -> None:
    env = _seed()
    today = date.today().isoformat()
    # Two monthly payments + one quarterly + one drop-in cash.
    for body in [
        {
            "member_id": env["member_ids"][0],
            "amount_cents": 25000,
            "payment_method": "cash",
            "subscription_id": env["s_monthly_id"],
            "paid_at": today,
        },
        {
            "member_id": env["member_ids"][0],
            "amount_cents": 25000,
            "payment_method": "cash",
            "subscription_id": env["s_monthly_id"],
            "paid_at": today,
        },
        {
            "member_id": env["member_ids"][1],
            "amount_cents": 70000,
            "payment_method": "credit_card",
            "subscription_id": env["s_quarterly_id"],
            "paid_at": today,
        },
        {
            "member_id": env["member_ids"][0],
            "amount_cents": 5000,
            "payment_method": "cash",
            "paid_at": today,
        },  # drop-in
    ]:
        r = client.post("/api/v1/payments", headers=env["staff_headers"], json=body)
        assert r.status_code == 201, r.text

    r = client.get("/api/v1/dashboard/revenue", headers=env["owner_headers"])
    assert r.status_code == 200
    body = r.json()
    # 25000 * 2 + 70000 + 5000 = 125000.
    assert body["this_month"]["cents"] == 125000

    # by_plan excludes the drop-in: 50000 monthly + 70000 quarterly = 120000.
    by_plan = {row["plan_id"]: row["cents"] for row in body["by_plan"]}
    assert by_plan[env["monthly_plan_id"]] == 50000
    assert by_plan[env["quarterly_plan_id"]] == 70000
    assert sum(by_plan.values()) == 120000

    # by_method covers all 4 payments (drop-in included).
    assert body["by_method"]["cash"] == 55000  # 25000 + 25000 + 5000
    assert body["by_method"]["credit_card"] == 70000

    # ARPM: 125000 cents / 2 distinct paying members = 62500.
    assert body["arpm_cents"] == 62500


def test_refund_subtracts_from_totals(client: TestClient) -> None:
    env = _seed()
    today = date.today().isoformat()
    p = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_ids"][0],
            "amount_cents": 25000,
            "payment_method": "cash",
            "subscription_id": env["s_monthly_id"],
            "paid_at": today,
        },
    ).json()
    # Refund 5000.
    client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 5000},
    )

    r = client.get("/api/v1/dashboard/revenue", headers=env["owner_headers"])
    body = r.json()
    assert body["this_month"]["cents"] == 20000
    by_plan = {row["plan_id"]: row["cents"] for row in body["by_plan"]}
    assert by_plan[env["monthly_plan_id"]] == 20000


def test_summary_mom_pct_with_last_month_data(client: TestClient) -> None:
    """Insert last-month payments via raw SQL (the API rejects future
    paid_at and friction-gates >30d backdate; raw SQL bypasses both)."""
    env = _seed()
    today = date.today()
    last_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=15)

    engine = create_engine(_sync_url())
    with Session(engine) as s:
        # Last month: 10000.
        s.execute(
            text(
                "INSERT INTO payments "
                "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                "VALUES (:t, :m, 10000, 'ILS', 'cash', :d)"
            ),
            {"t": env["tenant_id"], "m": env["member_ids"][0], "d": last_month_day},
        )
        # This month: 12000.
        s.execute(
            text(
                "INSERT INTO payments "
                "(tenant_id, member_id, amount_cents, currency, payment_method, paid_at) "
                "VALUES (:t, :m, 12000, 'ILS', 'cash', :d)"
            ),
            {"t": env["tenant_id"], "m": env["member_ids"][0], "d": today},
        )
        s.commit()
    engine.dispose()

    r = client.get("/api/v1/dashboard/revenue", headers=env["owner_headers"])
    body = r.json()
    assert body["this_month"]["cents"] == 12000
    assert body["last_month"]["cents"] == 10000
    # (12000 - 10000) / 10000 * 100 = 20.0
    assert body["mom_pct"] == 20.0


def test_coach_blocked_from_dashboard(client: TestClient) -> None:
    env = _seed()
    coach_id = None
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        coach_id = s.execute(
            text(
                "INSERT INTO users (email, password_hash, role, tenant_id, is_active) "
                "VALUES (:e, :p, 'coach', :t, true) RETURNING id"
            ),
            {
                "e": f"c-{uuid4().hex[:6]}@g.co",
                "p": hash_password("x"),
                "t": env["tenant_id"],
            },
        ).scalar_one()
        s.commit()
    engine.dispose()

    headers = _headers(coach_id, "coach", env["tenant_id"], os.environ["APP_SECRET_KEY"])
    r = client.get("/api/v1/dashboard/revenue", headers=headers)
    assert r.status_code == 403
