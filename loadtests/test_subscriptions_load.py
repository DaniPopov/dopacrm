"""Load test: Subscriptions CRUD + state transitions + event timeline.

Simulates the front-desk flow at a busy gym: enroll → view → freeze →
renew → cancel, plus the dashboard's "about to expire this week" query.
Runs as STAFF (subs mutations are staff+).

Setup (one-time):
    make up-dev
    make seed-test-gym-dev SLUG=loadtest
    # creates staff@loadtest.test / TestPass1!
    # also seeds an owner + plans

This script creates its own members on the fly (fresh phone each time),
because subscriptions need a member + a plan and we can't clobber
staff-owned data between users.

Run:
    uv run locust -f loadtests/test_subscriptions_load.py --host=http://localhost:8000
    → open http://localhost:8089

Headless:
    uv run locust -f loadtests/test_subscriptions_load.py --host=http://localhost:8000 \
        --headless -u 10 -r 2 -t 60s
"""

import random
import uuid

from locust import HttpUser, between, task

STAFF_EMAIL = "staff@loadtest.test"
STAFF_PASSWORD = "TestPass1!"


class GymFrontDesk(HttpUser):
    """Front-desk staff operating on member subscriptions."""

    wait_time = between(1, 3)
    headers: dict = {}
    # One plan used for all subs this VU creates. Loaded once on start.
    plan_id: str | None = None
    # Active sub pool: staff creates subs fresh per member, freezes/renews/cancels them.
    active_sub_ids: list[str] = []

    def on_start(self) -> None:
        """Log in + grab any active plan to enroll members in."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD},
        )
        if resp.status_code != 200:
            self.headers = {}
            return
        token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

        plans = self.client.get("/api/v1/plans", headers=self.headers)
        if plans.status_code == 200 and plans.json():
            self.plan_id = plans.json()[0]["id"]
        self.active_sub_ids = []

    def _create_member(self) -> str | None:
        """Helper: create a one-off member so we can enroll them."""
        if not self.headers:
            return None
        r = self.client.post(
            "/api/v1/members",
            headers=self.headers,
            json={
                "first_name": "Load",
                "last_name": "Member",
                "phone": f"05{uuid.uuid4().hex[:8]}",
            },
            name="/api/v1/members [setup]",
        )
        if r.status_code == 201:
            return r.json()["id"]
        return None

    # ── Tasks (weighted by realistic gym-ops frequency) ──────────────────

    @task(6)
    def list_subs(self) -> None:
        """GET /subscriptions — the member-list / dashboard query."""
        if not self.headers:
            return
        self.client.get("/api/v1/subscriptions", headers=self.headers)

    @task(4)
    def list_expiring_this_week(self) -> None:
        """GET /subscriptions?expires_within_days=7 — the about-to-expire widget.
        Uses the partial index on expires_at; cheap if indexed correctly."""
        if not self.headers:
            return
        self.client.get(
            "/api/v1/subscriptions?expires_within_days=7",
            headers=self.headers,
            name="/api/v1/subscriptions [expiring]",
        )

    @task(4)
    def enroll_new_member(self) -> None:
        """Full flow: create member + create sub. The hot path for front-desk."""
        if not self.headers or not self.plan_id:
            return
        member_id = self._create_member()
        if member_id is None:
            return
        method = random.choice(["cash", "credit_card", "standing_order"])
        body = {
            "member_id": member_id,
            "plan_id": self.plan_id,
            "payment_method": method,
        }
        if method != "standing_order":
            # Emulate staff setting a 30-day expires_at for cash/card
            body["expires_at"] = "2027-01-01"
        r = self.client.post(
            "/api/v1/subscriptions",
            headers=self.headers,
            json=body,
            name="/api/v1/subscriptions [enroll]",
        )
        if r.status_code == 201:
            self.active_sub_ids.append(r.json()["id"])

    @task(2)
    def view_sub_and_events(self) -> None:
        """GET /subscriptions/{id} + /events — the member detail page hit."""
        if not self.active_sub_ids:
            return
        sub_id = random.choice(self.active_sub_ids)
        self.client.get(
            f"/api/v1/subscriptions/{sub_id}",
            headers=self.headers,
            name="/api/v1/subscriptions/{id} [get]",
        )
        self.client.get(
            f"/api/v1/subscriptions/{sub_id}/events",
            headers=self.headers,
            name="/api/v1/subscriptions/{id}/events",
        )

    @task(1)
    def freeze_then_unfreeze(self) -> None:
        """Freeze + unfreeze cycle — touches the events table + member.status sync."""
        if not self.active_sub_ids:
            return
        sub_id = random.choice(self.active_sub_ids)
        freeze = self.client.post(
            f"/api/v1/subscriptions/{sub_id}/freeze",
            headers=self.headers,
            json={},
            name="/api/v1/subscriptions/{id}/freeze",
        )
        # Only unfreeze if freeze worked (409 if sub wasn't active)
        if freeze.status_code == 200:
            self.client.post(
                f"/api/v1/subscriptions/{sub_id}/unfreeze",
                headers=self.headers,
                name="/api/v1/subscriptions/{id}/unfreeze",
            )

    @task(1)
    def renew(self) -> None:
        """Push expires_at forward by the plan's billing period."""
        if not self.active_sub_ids:
            return
        sub_id = random.choice(self.active_sub_ids)
        self.client.post(
            f"/api/v1/subscriptions/{sub_id}/renew",
            headers=self.headers,
            json={},
            name="/api/v1/subscriptions/{id}/renew",
        )

    @task(1)
    def cancel(self) -> None:
        """Cancel — also removes this sub from the VU's pool."""
        if not self.active_sub_ids:
            return
        sub_id = self.active_sub_ids.pop()
        self.client.post(
            f"/api/v1/subscriptions/{sub_id}/cancel",
            headers=self.headers,
            json={"reason": "moved_away"},
            name="/api/v1/subscriptions/{id}/cancel",
        )
