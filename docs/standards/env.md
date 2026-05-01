# Environment Variables

> All env vars the app needs, grouped by service.
> This is the source of truth for `.env.example`.

## Loading Strategy

- Use `pydantic-settings` (`BaseSettings`) to load and validate env vars at startup
- App fails fast on missing required vars — no silent defaults for critical config
- Settings object is created once at startup, injected everywhere via DI

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

## Environment Files

| File | Purpose | Committed |
|------|---------|-----------|
| `.env.example` | Template with placeholder values | Yes |
| `.env` | Local development defaults | No |
| `.env.dev` | Dev/staging server overrides | No |
| `.env.prod` | Production values | No |

**Loading priority:** `.env` is the default. Override per environment via `ENV_FILE=.env.prod` or Docker Compose env_file directive.

---

## Variables

### App

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENV` | Yes | `development` | `development` / `staging` / `production` |
| `APP_DEBUG` | No | `false` | Enable debug mode (never true in production) |
| `APP_HOST` | No | `0.0.0.0` | Server bind host |
| `APP_PORT` | No | `8000` | Server bind port |
| `APP_LOG_LEVEL` | No | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `APP_LOG_FORMAT` | No | `json` | `json` (CloudWatch-friendly) or `console` (pretty for local terminal) |
| `APP_SERVICE_NAME` | No | `backend` | Container self-identifier in logs (`backend` / `worker` / `worker-beat`). Set per-container in compose. |
| `APP_SECRET_KEY` | Yes | — | Used for JWT signing. Min 32 chars |

### Postgres

Self-hosted in dev (Docker container) and prod (VPS). Future migration to RDS will keep the same env contract.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | asyncpg connection string (`postgresql+asyncpg://user:pass@host:5432/db`) |
| `DATABASE_DIRECT_URL` | No | — | Sync URL for Alembic migrations. Empty falls back to `DATABASE_URL`. |

### Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | — | Connection string (e.g. `redis://localhost:6379/0`) |

### RabbitMQ

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RABBITMQ_URL` | Yes | — | AMQP connection string (e.g. `amqp://guest:guest@localhost:5672//`) |

### AWS

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` | Yes | `il-central-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | Yes | — | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | IAM secret key |
| `AWS_S3_BUCKET` | Yes | — | S3 bucket for media storage |

### Sentry

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | Yes (prod) | — | Sentry project DSN |
| `SENTRY_ENVIRONMENT` | No | `APP_ENV` value | Environment tag in Sentry |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.1` | Performance monitoring sample rate |

### Celery

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CELERY_BROKER_URL` | No | `RABBITMQ_URL` value | Defaults to RabbitMQ URL |
| `CELERY_RESULT_BACKEND` | No | `REDIS_URL` value | Task result storage |

### Flower

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLOWER_PORT` | No | `5555` | Flower dashboard port |
| `FLOWER_BASIC_AUTH` | Yes (prod) | — | `user:password` for Flower dashboard |

---

## Per-Tenant vs Global

Important distinction:

| Scope | Storage | Example |
|-------|---------|---------|
| **Global** (same for all tenants) | Env vars | `DATABASE_URL`, `REDIS_URL`, `SENTRY_DSN` |
| **Per-tenant** (different per gym) | `tenants.features_enabled` JSONB + AWS Secrets Manager (when secrets land) | Feature flags today; future: payment processor keys, integration tokens |

Never put per-tenant secrets in env vars — they don't scale with multi-tenancy.

---

## Validation

All vars are validated at startup via `pydantic-settings`. App refuses to start if required vars are missing:

See `app/core/config.py` for the live shape — every env var listed
above maps to a Pydantic field there. Source-of-truth lives in code,
not this doc.
