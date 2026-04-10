"""Root test conftest — sets env vars needed by Settings before any app import.

These are test defaults so you can run `uv run pytest` from the terminal
without sourcing .env.dev. Values are harmless (test-not-real, localhost).
"""

import os

_TEST_ENV = {
    "APP_SECRET_KEY": "test-secret-key-minimum-32-characters-long!!",
    "APP_ENV": "development",
    "MONGODB_URI": "mongodb://localhost:27017",
    "MONGODB_DATABASE": "test",
    "NEON_DATABASE_URL": "postgresql://dopacrm:dopacrm@127.0.0.1:5432/dopacrm",
    "REDIS_URL": "redis://localhost:6379/0",
    "RABBITMQ_URL": "amqp://guest:guest@localhost:5672//",
    "AWS_ACCESS_KEY_ID": "test-not-real",
    "AWS_SECRET_ACCESS_KEY": "test-not-real",
    "AWS_S3_BUCKET": "test-bucket",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

# Now safe to import app
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
