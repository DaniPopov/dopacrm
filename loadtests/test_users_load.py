"""Load test: Users CRUD endpoints.

Simulates authenticated dashboard users browsing and managing users.
Tests DB connection pool, response times, and API rate limits under load.

Run:
    uv run locust -f loadtests/test_users_load.py --host=http://localhost:8000
    → open http://localhost:8089
    → set users + ramp-up → Start
"""

from locust import HttpUser, between, task


class DashboardUser(HttpUser):
    """Simulates an authenticated admin using the dashboard."""

    wait_time = between(1, 3)
    token: str | None = None
    headers: dict = {}

    def on_start(self):
        """Login once when the simulated user starts."""
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
        else:
            self.headers = {}

    @task(5)
    def list_users(self):
        """GET /api/v1/users — most common dashboard action."""
        self.client.get("/api/v1/users", headers=self.headers)

    @task(3)
    def get_my_profile(self):
        """GET /api/v1/auth/me — check who I am."""
        self.client.get("/api/v1/auth/me", headers=self.headers)

    @task(1)
    def health_check(self):
        """GET /health — always available, no auth."""
        self.client.get("/health")
