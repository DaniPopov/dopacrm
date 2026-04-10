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
| `APP_LOG_FORMAT` | No | `json` | `json` (Loki/Promtail-friendly) or `console` (pretty for local terminal) |
| `APP_SERVICE_NAME` | No | `backend` | Container self-identifier in logs (`backend` / `worker` / `worker-beat`). Set per-container in compose. |
| `APP_SECRET_KEY` | Yes | — | Used for JWT signing. Min 32 chars |

### MongoDB

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONGODB_URI` | Yes | — | Full connection string (e.g. `mongodb://localhost:27017`) |
| `MONGODB_DATABASE` | Yes | — | Database name (e.g. `assets_agent`) |

### Neon (Postgres)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEON_DATABASE_URL` | Yes | — | Pooled connection string from Neon dashboard |
| `NEON_DIRECT_URL` | No | — | Direct (non-pooled) URL for migrations only |

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

### WhatsApp (Meta Cloud API)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | Yes | — | Webhook verification token (set in Meta dashboard) |

> Per-tenant WhatsApp credentials (access_token, webhook_secret) are stored in
> AWS Secrets Manager and loaded via Config Service — NOT as env vars.

### Langfuse

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGFUSE_BASE_URL` | No | `https://cloud.langfuse.com` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | No (dev) / Yes (prod fallback) | — | Default Langfuse public key |
| `LANGFUSE_SECRET_KEY` | No (dev) / Yes (prod fallback) | — | Default Langfuse secret key |

> **Per-tenant override:** In production, each company's Langfuse keys live
> in MongoDB `company_config` (per the multi-tenancy plan). The env-var
> keys above act as a **dev/global fallback** when a tenant doesn't have
> its own keys configured. For dev, point them at a single shared
> Langfuse account.

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
| **Global** (same for all tenants) | Env vars | `MONGODB_URI`, `REDIS_URL`, `SENTRY_DSN` |
| **Per-tenant** (different per company) | MongoDB + Secrets Manager | WhatsApp tokens, Priority passwords, Langfuse keys |

Never put per-tenant secrets in env vars — they don't scale with multi-tenancy.

---

## Validation

All vars are validated at startup via `pydantic-settings`. App refuses to start if required vars are missing:

```python
class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_LOG_LEVEL: str = "INFO"
    APP_SECRET_KEY: str

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str

    # Neon
    NEON_DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # RabbitMQ
    RABBITMQ_URL: str

    # AWS
    AWS_REGION: str = "il-central-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_S3_BUCKET: str

    # WhatsApp
    WHATSAPP_VERIFY_TOKEN: str

    # Sentry
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Celery
    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.RABBITMQ_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```
