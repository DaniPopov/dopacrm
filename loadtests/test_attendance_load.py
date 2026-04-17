"""Load test: Attendance check-in flow (the highest-frequency write in the CRM).

Expected peak at a mid-sized gym is 200-300 check-ins during a 2-hour
evening rush (~2-3 QPS on /quota-check + /attendance). This script
simulates that — mixed members, mixed classes, realistic ratio of
reads (quota-check) to writes (record / undo).

Setup (one-time):
    make up-dev
    make seed-test-gym-dev SLUG=loadtest
    # Creates the basics. Then manually (for now — future: seed richer
    # attendance fixtures) enroll a few members in a plan so there are
    # live subscriptions to check in against.

Run:
    uv run locust -f loadtests/test_attendance_load.py --host=http://localhost:8000
    → open http://localhost:8089

Targets (documented in docs/features/attendance.md):
    - 99p /attendance/quota-check < 50ms at 10 VU.
    - 99p POST /attendance < 100ms at 10 VU.
    - Zero errors at 20 VU for 60s.

If the 99p creeps up: check EXPLAIN on count_effective_entries —
the partial index on (member_id, class_id, entered_at) WHERE
undone_at IS NULL should show an Index Only Scan.
"""

import random

from locust import HttpUser, between, task

STAFF_EMAIL = "staff@loadtest.test"
STAFF_PASSWORD = "TestPass1!"


class GymFrontDesk(HttpUser):
    """One VU = one front-desk terminal."""

    wait_time = between(1, 3)
    headers: dict = {}
    # Member + class pools loaded once per VU at start. If the seed is
    # empty, the VU idles.
    members: list[str] = []
    classes: list[str] = []
    # Track entries this VU recorded so it can undo some of them.
    recent_entries: list[str] = []

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD},
        )
        if resp.status_code != 200:
            self.headers = {}
            return
        token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

        members_resp = self.client.get("/api/v1/members?limit=200", headers=self.headers)
        if members_resp.status_code == 200:
            self.members = [m["id"] for m in members_resp.json()]
        classes_resp = self.client.get("/api/v1/classes", headers=self.headers)
        if classes_resp.status_code == 200:
            self.classes = [c["id"] for c in classes_resp.json()]
        self.recent_entries = []

    def _pick_pair(self) -> tuple[str, str] | None:
        if not self.members or not self.classes:
            return None
        return (random.choice(self.members), random.choice(self.classes))

    # ── Tasks (weighted for realism) ────────────────────────────

    @task(10)
    def quota_check(self) -> None:
        """Highest-frequency read — fires every time staff picks a member
        (even if they don't end up recording)."""
        if not self.headers:
            return
        pair = self._pick_pair()
        if pair is None:
            return
        member_id, class_id = pair
        self.client.get(
            f"/api/v1/attendance/quota-check?member_id={member_id}&class_id={class_id}",
            headers=self.headers,
            name="/api/v1/attendance/quota-check",
        )

    @task(6)
    def record_entry(self) -> None:
        """The actual check-in. Override=false to exercise the happy + quota
        rejection paths naturally."""
        if not self.headers:
            return
        pair = self._pick_pair()
        if pair is None:
            return
        member_id, class_id = pair
        r = self.client.post(
            "/api/v1/attendance",
            headers=self.headers,
            json={"member_id": member_id, "class_id": class_id},
            name="/api/v1/attendance [record]",
        )
        if r.status_code == 201:
            self.recent_entries.append(r.json()["id"])
            # Cap so the list doesn't grow unbounded
            if len(self.recent_entries) > 20:
                self.recent_entries.pop(0)

    @task(3)
    def list_recent(self) -> None:
        """Staff's 'recent check-ins' panel refresh."""
        if not self.headers:
            return
        self.client.get(
            "/api/v1/attendance?limit=10",
            headers=self.headers,
            name="/api/v1/attendance [list]",
        )

    @task(2)
    def member_summary(self) -> None:
        """Check-in header summary query. Hits once per member pick."""
        if not self.headers or not self.members:
            return
        member_id = random.choice(self.members)
        self.client.get(
            f"/api/v1/attendance/members/{member_id}/summary",
            headers=self.headers,
            name="/api/v1/attendance/members/{id}/summary",
        )

    @task(1)
    def undo(self) -> None:
        """Occasional undo — simulates staff correcting a mistake."""
        if not self.headers or not self.recent_entries:
            return
        entry_id = self.recent_entries.pop()
        self.client.post(
            f"/api/v1/attendance/{entry_id}/undo",
            headers=self.headers,
            json={},
            name="/api/v1/attendance/{id}/undo",
        )
