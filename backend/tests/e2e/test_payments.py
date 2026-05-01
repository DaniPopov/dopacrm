"""E2E tests for the Payments API.

Covers:
- Record happy path + auto-fields (currency snapshot, recorded_by)
- Append-only enforcement (no PATCH/DELETE endpoints)
- Refund happy path + the math edges (full / partial / over-cap /
  already-fully-refunded / refund-of-refund)
- Permission gates (staff records, owner refunds, coach blocked)
- Backdate flag friction
- Future-date rejection
- Cross-resource validation (sub belongs to same member)

Cross-tenant probes live in test_cross_tenant_isolation.py (additions
appended for the new endpoints).
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
    """Seed one tenant + every role + a member + an active sub on a
    monthly plan. Payments is basic (always on) so no flag needed."""
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

        member_id = s.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'M', 'X', :ph) RETURNING id"
            ),
            {"t": tenant_id, "ph": f"+972-{uuid4().hex[:9]}"},
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

        sub_id = s.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, started_at) "
                "VALUES (:t, :m, :p, 'active', 25000, 'ILS', :s) RETURNING id"
            ),
            {"t": tenant_id, "m": member_id, "p": membership_plan_id, "s": date.today()},
        ).scalar_one()

        s.commit()
    engine.dispose()

    secret = os.environ["APP_SECRET_KEY"]
    return {
        "tenant_id": str(tenant_id),
        "owner_id": str(users["owner"]),
        "owner_headers": _headers(users["owner"], "owner", tenant_id, secret),
        "sales_headers": _headers(users["sales"], "sales", tenant_id, secret),
        "staff_headers": _headers(users["staff"], "staff", tenant_id, secret),
        "coach_headers": _headers(users["coach"], "coach", tenant_id, secret),
        "member_id": str(member_id),
        "subscription_id": str(sub_id),
        "plan_id": str(membership_plan_id),
    }


# ── Record ───────────────────────────────────────────────────────────


def test_staff_can_record_payment(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 25000,
            "payment_method": "cash",
            "subscription_id": env["subscription_id"],
            "notes": "April monthly fee",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount_cents"] == 25000
    assert body["currency"] == "ILS"  # snapshot from tenant
    assert body["payment_method"] == "cash"
    assert body["paid_at"] == date.today().isoformat()


def test_record_payment_without_subscription_for_drop_in(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 5000,
            "payment_method": "cash",
            "notes": "drop-in yoga",
        },
    )
    assert r.status_code == 201
    assert r.json()["subscription_id"] is None


def test_coach_cannot_record_payment(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/payments",
        headers=env["coach_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    )
    assert r.status_code == 403


def test_zero_amount_rejected_at_schema(client: TestClient) -> None:
    env = _seed()
    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 0,
            "payment_method": "cash",
        },
    )
    assert r.status_code == 422


def test_negative_amount_rejected_at_schema(client: TestClient) -> None:
    """Refunds use the dedicated endpoint — the record endpoint doesn't
    accept negatives directly."""
    env = _seed()
    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": -1000,
            "payment_method": "cash",
        },
    )
    assert r.status_code == 422


def test_future_paid_at_rejected(client: TestClient) -> None:
    env = _seed()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
            "paid_at": tomorrow,
        },
    )
    assert r.status_code == 422
    assert r.json()["error"] == "PAYMENT_AMOUNT_INVALID"


def test_backdate_more_than_30_days_requires_flag(client: TestClient) -> None:
    env = _seed()
    forty_days_ago = (date.today() - timedelta(days=40)).isoformat()

    # Without the flag → 422.
    r1 = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
            "paid_at": forty_days_ago,
        },
    )
    assert r1.status_code == 422
    assert r1.json()["error"] == "PAYMENT_AMOUNT_INVALID"

    # With the flag → 201.
    r2 = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
            "paid_at": forty_days_ago,
            "backdate": True,
        },
    )
    assert r2.status_code == 201
    assert r2.json()["paid_at"] == forty_days_ago


def test_subscription_must_belong_to_same_member(client: TestClient) -> None:
    """A sub from another member in the same tenant — service rejects."""
    env = _seed()
    # Make a second member with no subscription.
    engine = create_engine(_sync_url())
    with Session(engine) as s:
        other_member = s.execute(
            text(
                "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                "VALUES (:t, 'O', 'M', :ph) RETURNING id"
            ),
            {"t": env["tenant_id"], "ph": f"+972-{uuid4().hex[:9]}"},
        ).scalar_one()
        s.commit()
    engine.dispose()

    r = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": str(other_member),
            "amount_cents": 1000,
            "payment_method": "cash",
            "subscription_id": env["subscription_id"],  # belongs to env["member_id"]
        },
    )
    assert r.status_code == 404


# ── List + get ───────────────────────────────────────────────────────


def test_list_member_payments_endpoint(client: TestClient) -> None:
    env = _seed()
    client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 25000,
            "payment_method": "cash",
            "subscription_id": env["subscription_id"],
        },
    )
    r = client.get(
        f"/api/v1/members/{env['member_id']}/payments",
        headers=env["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_filter_by_method(client: TestClient) -> None:
    env = _seed()
    client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    )
    client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 2000,
            "payment_method": "credit_card",
        },
    )

    r = client.get(
        "/api/v1/payments?method=cash",
        headers=env["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["amount_cents"] == 1000


def test_get_one_payment(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    ).json()
    r = client.get(
        f"/api/v1/payments/{created['id']}",
        headers=env["owner_headers"],
    )
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_returns_404(client: TestClient) -> None:
    env = _seed()
    r = client.get(
        f"/api/v1/payments/{uuid4()}",
        headers=env["owner_headers"],
    )
    assert r.status_code == 404


# ── Append-only ──────────────────────────────────────────────────────


def test_no_patch_endpoint(client: TestClient) -> None:
    """Append-only enforced at the API surface — no PATCH route exists."""
    env = _seed()
    created = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    ).json()
    r = client.patch(
        f"/api/v1/payments/{created['id']}",
        headers=env["owner_headers"],
        json={"amount_cents": 9999},
    )
    assert r.status_code == 405


def test_no_delete_endpoint(client: TestClient) -> None:
    env = _seed()
    created = client.post(
        "/api/v1/payments",
        headers=env["staff_headers"],
        json={
            "member_id": env["member_id"],
            "amount_cents": 1000,
            "payment_method": "cash",
        },
    ).json()
    r = client.delete(
        f"/api/v1/payments/{created['id']}",
        headers=env["owner_headers"],
    )
    assert r.status_code == 405


# ── Refund ───────────────────────────────────────────────────────────


def _record(client, env, *, amount=25000, method="cash", sub=True):
    body = {
        "member_id": env["member_id"],
        "amount_cents": amount,
        "payment_method": method,
    }
    if sub:
        body["subscription_id"] = env["subscription_id"]
    r = client.post("/api/v1/payments", headers=env["staff_headers"], json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_owner_can_full_refund(client: TestClient) -> None:
    env = _seed()
    p = _record(client, env, amount=25000)
    r = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"reason": "test"},
    )
    assert r.status_code == 200
    refund = r.json()
    assert refund["amount_cents"] == -25000
    assert refund["refund_of_payment_id"] == p["id"]
    # Subscription_id copied so by-plan reports group correctly.
    assert refund["subscription_id"] == p["subscription_id"]


def test_owner_can_partial_refund(client: TestClient) -> None:
    env = _seed()
    p = _record(client, env, amount=25000)
    r = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 10000, "reason": "partial"},
    )
    assert r.status_code == 200
    assert r.json()["amount_cents"] == -10000


def test_staff_cannot_refund(client: TestClient) -> None:
    env = _seed()
    p = _record(client, env, amount=25000)
    r = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["staff_headers"],
        json={"reason": "test"},
    )
    assert r.status_code == 403


def test_refund_exceeds_remaining_blocked(client: TestClient) -> None:
    env = _seed()
    p = _record(client, env, amount=25000)
    # Refund 20000.
    r1 = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 20000},
    )
    assert r1.status_code == 200

    # Try to refund another 10000 — only 5000 left.
    r2 = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 10000},
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "PAYMENT_REFUND_EXCEEDS_ORIGINAL"


def test_already_fully_refunded_blocked(client: TestClient) -> None:
    """After a full refund, the next attempt gets the dedicated
    ``ALREADY_FULLY_REFUNDED`` code so the UI hides the button."""
    env = _seed()
    p = _record(client, env, amount=25000)
    client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={},
    )
    r = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 100},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "PAYMENT_ALREADY_FULLY_REFUNDED"


def test_refund_of_refund_blocked(client: TestClient) -> None:
    """Cleaner audit story — refund chains are flat. The refund row's
    ``refund_of_payment_id`` must point at a non-refund row."""
    env = _seed()
    p = _record(client, env, amount=25000)
    refund = client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 5000},
    ).json()

    r = client.post(
        f"/api/v1/payments/{refund['id']}/refund",
        headers=env["owner_headers"],
        json={"amount_cents": 1000},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "PAYMENT_AMOUNT_INVALID"


# ── List filtering for refund inclusion ──────────────────────────────


def test_list_with_include_refunds_false_excludes_refund_rows(
    client: TestClient,
) -> None:
    env = _seed()
    p = _record(client, env, amount=10000)
    client.post(
        f"/api/v1/payments/{p['id']}/refund",
        headers=env["owner_headers"],
        json={},
    )

    with_refunds = client.get("/api/v1/payments", headers=env["owner_headers"]).json()
    assert len(with_refunds) == 2

    without_refunds = client.get(
        "/api/v1/payments?include_refunds=false",
        headers=env["owner_headers"],
    ).json()
    assert len(without_refunds) == 1
    assert without_refunds[0]["id"] == p["id"]
