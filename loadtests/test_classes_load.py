"""Load test: class-catalog endpoints.

Simulates a gym owner defining + reading their class catalog under load.

Unlike the admin load tests, this one runs as a TENANT user (owner):
class ops are gym-scoped (super_admin is rejected by the service layer),
so we need a tenant token. Make sure a tenant exists first and an owner
user is seeded — the easiest way is:

    make up-dev
    make seed-test-gym-dev SLUG=loadtest
    # creates owner@loadtest.test / TestPass1!

Run:
    uv run locust -f loadtests/test_classes_load.py --host=http://localhost:8000
    → open http://localhost:8089

Headless (CI-friendly):
    uv run locust -f loadtests/test_classes_load.py --host=http://localhost:8000 \
        --headless -u 10 -r 2 -t 30s
"""

import uuid

from locust import HttpUser, between, task

OWNER_EMAIL = "owner@loadtest.test"
OWNER_PASSWORD = "TestPass1!"


class GymOwner(HttpUser):
    """Simulates an owner managing their class catalog."""

    wait_time = between(1, 3)
    token: str | None = None
    headers: dict = {}
    created_ids: list[str] = []

    def on_start(self) -> None:
        """Log in once as the seeded owner. Skip tasks if creds fail."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.created_ids = []
        else:
            # Fresh DB — tell the runner to skip this user
            self.headers = {}

    @task(5)
    def list_classes(self) -> None:
        """GET /classes — most common op, staff + owner hit this to pick a class."""
        if not self.headers:
            return
        self.client.get("/api/v1/classes", headers=self.headers)

    @task(3)
    def create_and_get(self) -> None:
        """POST + GET — create a class, fetch it. Simulates owner setup flow."""
        if not self.headers:
            return
        name = f"LoadClass-{uuid.uuid4().hex[:8]}"
        r = self.client.post(
            "/api/v1/classes",
            headers=self.headers,
            json={"name": name, "color": "#3B82F6"},
            name="/api/v1/classes [create]",
        )
        if r.status_code == 201:
            class_id = r.json()["id"]
            self.created_ids.append(class_id)
            self.client.get(
                f"/api/v1/classes/{class_id}",
                headers=self.headers,
                name="/api/v1/classes/{id} [get]",
            )

    @task(2)
    def update_class(self) -> None:
        """PATCH — owner tweaks color or description."""
        if not self.headers or not self.created_ids:
            return
        class_id = self.created_ids[-1]
        self.client.patch(
            f"/api/v1/classes/{class_id}",
            headers=self.headers,
            json={"color": "#10B981"},
            name="/api/v1/classes/{id} [update]",
        )

    @task(1)
    def deactivate_class(self) -> None:
        """POST deactivate — owner retires a class they no longer offer."""
        if not self.headers or not self.created_ids:
            return
        class_id = self.created_ids.pop(0)
        self.client.post(
            f"/api/v1/classes/{class_id}/deactivate",
            headers=self.headers,
            name="/api/v1/classes/{id}/deactivate",
        )
