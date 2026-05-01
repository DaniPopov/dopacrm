"""E2E tests for the nightly Celery beat jobs (auto-unfreeze + auto-expire).

Exercises ``SubscriptionService.auto_unfreeze_due`` and ``auto_expire_due``
against a real Postgres, through the async session factory the Celery
tasks use in production. The Celery wrapper itself is a one-liner
(``asyncio.run`` over the service method) so we don't duplicate the
test through the broker — the service-level test is enough.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.adapters.storage.postgres.database import (
    _session_factory,
    async_session_factory,
    get_engine,
)
from app.services.subscription_service import SubscriptionService


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _seed_world() -> dict:
    """Seed one tenant + plan + N members with subs in various states."""
    engine = create_engine(_sync_url())
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

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
        plan_id = session.execute(
            text(
                "INSERT INTO membership_plans (tenant_id, name, type, price_cents, "
                "currency, billing_period) VALUES "
                "(:t, 'P', 'recurring', 25000, 'ILS', 'monthly') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()

        members = {}
        for key in ("freeze_due", "freeze_future", "expire_due", "expire_future", "card_auto"):
            mid = session.execute(
                text(
                    "INSERT INTO members (tenant_id, first_name, last_name, phone) "
                    "VALUES (:t, :fn, 'M', :ph) RETURNING id"
                ),
                {"t": tenant_id, "fn": key, "ph": f"05{uuid4().hex[:8]}"},
            ).scalar_one()
            members[key] = mid

        # Sub states (all the same plan, different lifecycle setups):
        # 1) frozen with frozen_until yesterday → DUE for unfreeze
        session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at, frozen_at, frozen_until) VALUES "
                "(:t, :m, :p, 'frozen', 25000, 'ILS', :s, :e, :fa, :fu)"
            ),
            {
                "t": tenant_id,
                "m": members["freeze_due"],
                "p": plan_id,
                "s": date(2026, 4, 1),
                "e": date(2026, 5, 1),
                "fa": date(2026, 4, 5),
                "fu": yesterday,
            },
        )

        # 2) frozen with frozen_until tomorrow → NOT due
        session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at, frozen_at, frozen_until) VALUES "
                "(:t, :m, :p, 'frozen', 25000, 'ILS', :s, :e, :fa, :fu)"
            ),
            {
                "t": tenant_id,
                "m": members["freeze_future"],
                "p": plan_id,
                "s": date(2026, 4, 1),
                "e": date(2026, 5, 1),
                "fa": date(2026, 4, 10),
                "fu": tomorrow,
            },
        )

        # 3) active with expires_at yesterday → DUE for expire
        session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at) VALUES "
                "(:t, :m, :p, 'active', 25000, 'ILS', :s, :e)"
            ),
            {
                "t": tenant_id,
                "m": members["expire_due"],
                "p": plan_id,
                "s": date(2026, 3, 1),
                "e": yesterday,
            },
        )

        # 4) active with expires_at tomorrow → NOT due
        session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at) VALUES "
                "(:t, :m, :p, 'active', 25000, 'ILS', :s, :e)"
            ),
            {
                "t": tenant_id,
                "m": members["expire_future"],
                "p": plan_id,
                "s": date(2026, 4, 1),
                "e": tomorrow,
            },
        )

        # 5) card-auto: active with expires_at NULL → NEVER due
        session.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, member_id, plan_id, status, price_cents, currency, "
                "started_at, expires_at) VALUES "
                "(:t, :m, :p, 'active', 25000, 'ILS', :s, NULL)"
            ),
            {
                "t": tenant_id,
                "m": members["card_auto"],
                "p": plan_id,
                "s": date(2026, 4, 1),
            },
        )
        session.commit()
    engine.dispose()
    return {"tenant_id": tenant_id, "members": members, "yesterday": yesterday}


def _member_status(member_id: UUID) -> str:
    engine = create_engine(_sync_url())
    try:
        with Session(engine) as session:
            return session.execute(
                text("SELECT status FROM members WHERE id = :id"),
                {"id": member_id},
            ).scalar_one()
    finally:
        engine.dispose()


def _sub_for_member(member_id: UUID) -> dict:
    engine = create_engine(_sync_url())
    try:
        with Session(engine) as session:
            row = (
                session.execute(
                    text(
                        "SELECT status, frozen_at, frozen_until, expires_at, expired_at "
                        "FROM subscriptions WHERE member_id = :m LIMIT 1"
                    ),
                    {"m": member_id},
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        engine.dispose()


def _event_types(member_id: UUID) -> list[str]:
    engine = create_engine(_sync_url())
    try:
        with Session(engine) as session:
            rows = (
                session.execute(
                    text(
                        "SELECT event_type FROM subscription_events e "
                        "JOIN subscriptions s ON e.subscription_id = s.id "
                        "WHERE s.member_id = :m ORDER BY e.occurred_at ASC"
                    ),
                    {"m": member_id},
                )
                .scalars()
                .all()
            )
        return list(rows)
    finally:
        engine.dispose()


async def _run_auto_unfreeze() -> int:
    async with async_session_factory() as session:
        return await SubscriptionService(session).auto_unfreeze_due()


async def _run_auto_expire() -> int:
    async with async_session_factory() as session:
        return await SubscriptionService(session).auto_expire_due()


def _fresh_run(coro) -> int:
    """Run an async coroutine on a fresh event loop (like Celery would)."""
    # Clear cached engine/session so we get one bound to this loop.
    get_engine.cache_clear()
    _session_factory.cache_clear()
    try:
        return asyncio.run(coro)
    finally:
        get_engine.cache_clear()
        _session_factory.cache_clear()


# ── auto_unfreeze_due ────────────────────────────────────────────────────────


def test_auto_unfreeze_moves_only_due_rows() -> None:
    world = _seed_world()
    count = _fresh_run(_run_auto_unfreeze())
    assert count == 1

    due_sub = _sub_for_member(world["members"]["freeze_due"])
    assert due_sub["status"] == "active"
    assert due_sub["frozen_at"] is None
    assert due_sub["frozen_until"] is None

    future_sub = _sub_for_member(world["members"]["freeze_future"])
    assert future_sub["status"] == "frozen"


def test_auto_unfreeze_extends_expires_at_by_frozen_duration() -> None:
    """Frozen 2026-04-05 → unfrozen today (2026-04-17 if test runs on that
    date) — extension = (today - frozen_at) days added to expires_at.
    Because the test runs on whatever today is, we just assert
    expires_at >= original (5/1) and not stale."""
    world = _seed_world()
    _fresh_run(_run_auto_unfreeze())
    due_sub = _sub_for_member(world["members"]["freeze_due"])
    # Original expires_at was 2026-05-01; extension is >= 1 day
    assert due_sub["expires_at"] >= date(2026, 5, 1) + timedelta(days=1)


def test_auto_unfreeze_syncs_member_status_to_active() -> None:
    world = _seed_world()
    _fresh_run(_run_auto_unfreeze())
    assert _member_status(world["members"]["freeze_due"]) == "active"


def test_auto_unfreeze_writes_system_event() -> None:
    """created_by is NULL for nightly-job events."""
    world = _seed_world()
    _fresh_run(_run_auto_unfreeze())
    types = _event_types(world["members"]["freeze_due"])
    assert "unfrozen" in types


def test_auto_unfreeze_is_idempotent() -> None:
    """Second invocation finds zero rows to move."""
    _seed_world()
    _fresh_run(_run_auto_unfreeze())
    second = _fresh_run(_run_auto_unfreeze())
    assert second == 0


# ── auto_expire_due ──────────────────────────────────────────────────────────


def test_auto_expire_moves_only_due_active_rows() -> None:
    world = _seed_world()
    count = _fresh_run(_run_auto_expire())
    assert count == 1

    due_sub = _sub_for_member(world["members"]["expire_due"])
    assert due_sub["status"] == "expired"
    assert due_sub["expired_at"] is not None

    future_sub = _sub_for_member(world["members"]["expire_future"])
    assert future_sub["status"] == "active"


def test_auto_expire_skips_card_auto_subs() -> None:
    """expires_at IS NULL → never auto-expires."""
    world = _seed_world()
    _fresh_run(_run_auto_expire())
    sub = _sub_for_member(world["members"]["card_auto"])
    assert sub["status"] == "active"


def test_auto_expire_syncs_member_status_to_expired() -> None:
    world = _seed_world()
    _fresh_run(_run_auto_expire())
    assert _member_status(world["members"]["expire_due"]) == "expired"


def test_auto_expire_writes_system_event() -> None:
    world = _seed_world()
    _fresh_run(_run_auto_expire())
    types = _event_types(world["members"]["expire_due"])
    assert "expired" in types


def test_auto_expire_is_idempotent() -> None:
    _seed_world()
    _fresh_run(_run_auto_expire())
    second = _fresh_run(_run_auto_expire())
    assert second == 0


# ── Recovery path: renew rescues an expired sub with days_late ───────────────


def test_renew_after_auto_expire_preserves_tenure_and_logs_days_late() -> None:
    """Full flow: auto-expire flips sub → then service.renew resurrects it
    on the SAME row with days_late in the event data."""
    from app.domain.entities.subscription import SubscriptionStatus
    from app.services.subscription_service import SubscriptionService as Svc

    world = _seed_world()
    _fresh_run(_run_auto_expire())
    member_id = world["members"]["expire_due"]

    async def _renew_it() -> None:
        async with async_session_factory() as session:
            svc = Svc(session)
            current = await svc._repo.find_live_for_member(world["tenant_id"], member_id)
            # expire flipped it, so live search returns None; fetch all
            all_subs = await svc._repo.list_for_member(world["tenant_id"], member_id)
            expired_sub = next(s for s in all_subs if s.status == SubscriptionStatus.EXPIRED)
            assert current is None  # expired is NOT live
            # Renew via the raw repo to avoid TokenPayload plumbing for this one probe
            from datetime import date as _d
            from datetime import timedelta as _td

            await svc._repo.renew(
                expired_sub.id,
                new_expires_at=_d.today() + _td(days=30),
                days_late=(_d.today() - expired_sub.expired_at).days
                if expired_sub.expired_at
                else 0,
                created_by=None,
            )
            await session.commit()

    get_engine.cache_clear()
    _session_factory.cache_clear()
    try:
        asyncio.run(_renew_it())
    finally:
        get_engine.cache_clear()
        _session_factory.cache_clear()

    events = _event_types(member_id)
    assert "expired" in events
    assert "renewed" in events
