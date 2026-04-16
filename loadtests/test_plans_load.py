"""Load test: Membership Plans CRUD + entitlements.

Simulates a gym owner defining + maintaining the plan catalog. Runs as
a TENANT user (owner) — plan ops are gym-scoped.

Setup (one-time):
    make up-dev
    make seed-test-gym-dev SLUG=loadtest
    # creates owner@loadtest.test / TestPass1!

Run:
    uv run locust -f loadtests/test_plans_load.py --host=http://localhost:8000
    → open http://localhost:8089

Headless:
    uv run locust -f loadtests/test_plans_load.py --host=http://localhost:8000 \
        --headless -u 10 -r 2 -t 30s
"""

import uuid

from locust import HttpUser, between, task

OWNER_EMAIL = "owner@loadtest.test"
OWNER_PASSWORD = "TestPass1!"


class GymOwner(HttpUser):
    """Simulates an owner managing their plan catalog."""

    wait_time = between(1, 3)
    token: str | None = None
    headers: dict = {}
    created_ids: list[str] = []

    def on_start(self) -> None:
        """Log in once as the seeded owner; skip tasks if creds fail."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.created_ids = []
        else:
            self.headers = {}

    @task(5)
    def list_plans(self) -> None:
        """GET /plans — most common op, staff + owner check the catalog."""
        if not self.headers:
            return
        self.client.get("/api/v1/plans", headers=self.headers)

    @task(3)
    def create_and_get(self) -> None:
        """POST + GET — owner defines a new plan then reads it back."""
        if not self.headers:
            return
        name = f"LoadPlan-{uuid.uuid4().hex[:8]}"
        r = self.client.post(
            "/api/v1/plans",
            headers=self.headers,
            json={
                "name": name,
                "type": "recurring",
                "price_cents": 25000,
                "currency": "ILS",
                "billing_period": "monthly",
            },
            name="/api/v1/plans [create]",
        )
        if r.status_code == 201:
            plan_id = r.json()["id"]
            self.created_ids.append(plan_id)
            self.client.get(
                f"/api/v1/plans/{plan_id}",
                headers=self.headers,
                name="/api/v1/plans/{id} [get]",
            )

    @task(2)
    def update_plan(self) -> None:
        """PATCH — owner adjusts price or description on a previously created plan."""
        if not self.headers or not self.created_ids:
            return
        plan_id = self.created_ids[-1]
        self.client.patch(
            f"/api/v1/plans/{plan_id}",
            headers=self.headers,
            json={"price_cents": 30000},
            name="/api/v1/plans/{id} [update]",
        )

    @task(1)
    def deactivate_plan(self) -> None:
        """POST deactivate — owner retires an old plan."""
        if not self.headers or not self.created_ids:
            return
        plan_id = self.created_ids.pop(0)
        self.client.post(
            f"/api/v1/plans/{plan_id}/deactivate",
            headers=self.headers,
            name="/api/v1/plans/{id}/deactivate",
        )
