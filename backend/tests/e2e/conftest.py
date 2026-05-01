"""E2E test fixtures — sync TestClient.

Each test gets its own TestClient (its own event loop). The app's cached
async engine is cleared between tests so it creates a fresh engine on
the new loop. Rate limit Redis keys are also cleared.
"""

from __future__ import annotations

import os

import pytest
import redis as sync_redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.adapters.storage.postgres import Base
from app.adapters.storage.postgres.database import _session_factory, get_engine
from app.adapters.storage.redis.client import get_redis
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.main import app

_DEFAULT_DB_URL = "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm"


def _get_sync_url() -> str:
    url = os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _assert_safe_to_truncate(url: str) -> None:
    """Refuse to TRUNCATE a non-test database.

    The ``_clean_db`` fixture wipes every table on every test. Pointing
    it at the dev database (or worse, prod) is destructive. This guard
    fails loudly if the URL doesn't look like a local test target.

    Allowed: ``localhost`` / ``127.0.0.1`` host. Anything else demands
    an explicit opt-in via ``DOPACRM_TEST_DB_CONFIRM=1`` so a developer
    has to think twice before wiring tests to a remote DB.

    Real incident this guard prevents: 2026-04-30, the e2e suite was
    run against the manually-curated dev DB and CASCADE-truncated all
    tenants/members/payments. Fast assertion + clear error message
    beats a Slack apology.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    safe_hosts = {"localhost", "127.0.0.1", "::1", "postgres"}

    if host in safe_hosts:
        return
    if os.environ.get("DOPACRM_TEST_DB_CONFIRM") == "1":
        return

    raise RuntimeError(
        f"Refusing to TRUNCATE database at {host!r} — only localhost/127.0.0.1 "
        f"are auto-allowed. Set DOPACRM_TEST_DB_CONFIRM=1 to override "
        f"(double-check you're not pointed at production first)."
    )


@pytest.fixture
def client():
    """Fresh TestClient per test — clears async engine cache so each test
    gets a new engine on its own event loop."""
    # Clear ALL app-level caches so each test gets fresh connections
    # on the new event loop (TestClient creates its own loop)
    get_engine.cache_clear()
    _session_factory.cache_clear()
    get_redis.cache_clear()
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_engine.cache_clear()
    _session_factory.cache_clear()
    get_redis.cache_clear()


@pytest.fixture(autouse=True)
def _clean_db():
    """Clean DB tables + Redis rate limit keys before and after each test."""
    engine = create_engine(_get_sync_url())
    Base.metadata.create_all(engine)

    # Preserve seeded reference data (saas_plans) — integration tests
    # shouldn't pollute data that the dev DB depends on.
    _preserved = {"saas_plans", "alembic_version"}

    def _clean():
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in _preserved:
                    continue
                conn.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))
        # Clear rate limit keys
        r = sync_redis.Redis(host="localhost", port=6379)
        for key in r.scan_iter("rate:*"):
            r.delete(key)
        r.close()

    _clean()
    yield
    _clean()
    engine.dispose()


@pytest.fixture
def seed_super_admin() -> dict:
    """Seed a super_admin via sync SQL."""
    engine = create_engine(_get_sync_url())
    pwd_hash = hash_password("testpass123")
    with Session(engine) as session:
        result = session.execute(
            text(
                "INSERT INTO users (email, password_hash, role, is_active) "
                "VALUES (:email, :pwd, :role, true) RETURNING id"
            ),
            {"email": "testadmin@test.com", "pwd": pwd_hash, "role": "super_admin"},
        )
        user_id = result.scalar_one()
        session.commit()
    engine.dispose()
    return {"id": str(user_id), "email": "testadmin@test.com"}


@pytest.fixture
def super_admin_token(seed_super_admin: dict) -> str:
    return create_access_token(
        user_id=seed_super_admin["id"],
        role="super_admin",
        tenant_id=None,
        secret_key=os.environ["APP_SECRET_KEY"],
    )


@pytest.fixture
def auth_headers(super_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {super_admin_token}"}
