"""E2E tests for rate limiting.

Login is the only endpoint with a strict per-IP limit (10/min) — brute-force
protection. These tests fire rapid requests and assert that the 11th gets
blocked with 429.

The ``_clean_db`` fixture clears ``rate:*`` keys in Redis between tests so
they don't bleed into each other.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_rate_limit_blocks_after_10_attempts(client: TestClient) -> None:
    """Fire 11 failing login attempts — the 11th must be 429."""
    payload = {"email": "nobody@nowhere.com", "password": "wrong"}

    # First 10 requests: 401 (wrong credentials, but not rate limited yet)
    for i in range(10):
        resp = client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code == 401, f"attempt {i + 1} expected 401, got {resp.status_code}"

    # 11th request: 429
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 429
    detail = resp.json()["detail"]
    assert "Rate limit" in detail
    # Retry-After header should be present
    assert "retry-after" in {k.lower() for k in resp.headers}


def test_login_rate_limit_allows_fresh_start_after_cleanup(client: TestClient) -> None:
    """After ``_clean_db`` resets Redis keys, a new test starts from zero.

    This test is intentionally run after the blocking test to verify the
    cleanup fixture actually clears rate:* keys. If the fixture didn't
    work, this test would already be rate-limited.
    """
    # Fire a single login — should NOT be rate limited because the
    # previous test's counters were cleared.
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.com", "password": "wrong"},
    )
    assert resp.status_code == 401  # 401 = still hit the handler, not 429


def test_rate_limit_key_is_per_ip(client: TestClient) -> None:
    """Different IPs should be tracked separately.

    TestClient always uses the same IP (127.0.0.1) so we simulate a
    different one via X-Forwarded-For header.
    """
    payload = {"email": "nobody@nowhere.com", "password": "wrong"}

    # Fire 10 from the default client IP (uses all 10 of that bucket)
    for _ in range(10):
        client.post("/api/v1/auth/login", json=payload)

    # 11th from the same IP → 429
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 429

    # But a different IP (via X-Forwarded-For) should still have its own
    # 10-request budget
    resp = client.post(
        "/api/v1/auth/login",
        json=payload,
        headers={"X-Forwarded-For": "10.20.30.40"},
    )
    assert resp.status_code == 401  # 401, not 429 — fresh bucket
