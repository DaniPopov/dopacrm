"""Load test: Tenants CRUD endpoints.

Simulates a super_admin managing gyms on the platform.
Tests DB connection pool, response times, and API rate limits under load.

Run:
    uv run locust -f loadtests/test_tenants_load.py --host=http://localhost:8000
    → open http://localhost:8089
    → set users + ramp-up → Start

Or headless (CI-friendly):
    uv run locust -f loadtests/test_tenants_load.py --host=http://localhost:8000 \
        --headless -u 10 -r 2 -t 30s
"""

import uuid

from locust import HttpUser, between, task


class PlatformAdmin(HttpUser):
    """Simulates a super_admin managing tenants."""

    wait_time = between(1, 3)
    token: str | None = None
    headers: dict = {}
    created_ids: list[str] = []

    def on_start(self):
        """Login once as super_admin."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@dopacrm.com",
                "password": "Admin@12345",
            },
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.created_ids = []
        else:
            self.headers = {}

    @task(5)
    def list_tenants(self):
        """GET /api/v1/tenants — most common admin action."""
        self.client.get("/api/v1/tenants", headers=self.headers)

    @task(3)
    def create_and_get_tenant(self):
        """POST + GET — onboard a gym then fetch it."""
        slug = f"load-{uuid.uuid4().hex[:8]}"
        resp = self.client.post(
            "/api/v1/tenants",
            headers=self.headers,
            json={"slug": slug, "name": f"Load Test Gym {slug}"},
            name="/api/v1/tenants [create]",
        )
        if resp.status_code == 201:
            tenant_id = resp.json()["id"]
            self.created_ids.append(tenant_id)
            self.client.get(
                f"/api/v1/tenants/{tenant_id}",
                headers=self.headers,
                name="/api/v1/tenants/{id} [get]",
            )

    @task(2)
    def update_tenant(self):
        """PATCH — update a previously created tenant."""
        if not self.created_ids:
            return
        tenant_id = self.created_ids[-1]
        self.client.patch(
            f"/api/v1/tenants/{tenant_id}",
            headers=self.headers,
            json={"name": f"Updated Gym {uuid.uuid4().hex[:6]}"},
            name="/api/v1/tenants/{id} [update]",
        )

    @task(1)
    def suspend_tenant(self):
        """POST suspend — suspend a previously created tenant."""
        if not self.created_ids:
            return
        tenant_id = self.created_ids.pop(0)
        self.client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            headers=self.headers,
            name="/api/v1/tenants/{id}/suspend",
        )
