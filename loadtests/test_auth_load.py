"""Load test: Auth endpoints.

Tests login rate limiting and token validation under concurrent load.

Run:
    uv run locust -f loadtests/test_auth_load.py --host=http://localhost:8000
    → open http://localhost:8089
    → set users + ramp-up → Start

Or headless (CI-friendly):
    uv run locust -f loadtests/test_auth_load.py --host=http://localhost:8000 \
        --headless -u 20 -r 5 -t 30s
"""

from locust import HttpUser, between, task


class AuthUser(HttpUser):
    """Simulates a user logging in repeatedly — tests rate limiting."""

    wait_time = between(1, 3)

    @task
    def login(self):
        """POST /api/v1/auth/login — should hit 429 after 10 requests/min."""
        self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@dopacrm.com",
                "password": "Admin@12345",
            },
            name="/api/v1/auth/login",
        )
