# Project Structure

> Full file tree for the assets-agent codebase.
> This is the canonical layout — follow it when adding new files.

## Root

```
assets-agent/
├── backend/                    # Python service — Dockerfile, app code, tests
│   ├── Dockerfile              # python:3.13-slim + uv
│   ├── app/                    # Application code (importable as `app.*`)
│   ├── tests/                  # All tests (pytest)
│   ├── migrations/             # Alembic migrations (Postgres)
│   └── scripts/                # One-off scripts (seed data, manual ops)
├── docs/                       # Documentation
│   ├── notion_copy.md          # Full project spec from Notion
│   └── standards/              # Coding & architecture standards
├── releases/                   # Release notes per version (empty until first ship)
│   └── .gitkeep
├── .claude/                    # Claude Code config (committed to git)
│   ├── settings.json           # Hooks
│   └── commands/               # Slash commands for all devs
├── .github/                    # GitHub Actions CI/CD
│   └── workflows/
│       └── ci.yml              # ruff, pytest, gitleaks, pip-audit, docker-build
├── docker-compose.dev.yml      # Local dev orchestration (8 services)
├── Makefile                    # make up-dev / build-dev / down-dev / logs-dev / urls-dev / ...
├── pyproject.toml              # Python project config (deps, ruff, pytest, hatchling)
├── uv.lock                     # Reproducible dep lock — committed
├── .pre-commit-config.yaml     # ruff (+ auto-fix), gitleaks, basic hygiene
├── .dockerignore
├── .env.example                # Env var template (committed)
├── .env.dev                    # Local dev env (gitignored)
├── .gitignore
├── CLAUDE.md                   # AI context file
└── README.md
```

> **Package import path:** Code lives at `backend/app/` on disk but is installed
> via hatchling (`[tool.hatch.build.targets.wheel] packages = ["backend/app"]`)
> as the package `app`. Always import as `from app.domain... import ...`,
> never `from backend.app...`.

---

## App — The 4 Layers

```
backend/app/
├── __init__.py
├── main.py                     # FastAPI app factory + lifespan
├── bootstrap.py                # Wires adapters → services → routes (DI)
│
├── core/                       # Shared infrastructure (not a layer)
│   ├── __init__.py
│   ├── config.py               # Pydantic Settings (env var loading)
│   ├── celery_app.py           # Celery app instance + queue config
│   ├── logger.py               # structlog setup (JSON / console renderers)
│   └── time.py                 # Israel timezone helpers (now / utcnow / to_israel / to_utc)
│
├── api/                        # LAYER 1: ENTRY
│   ├── __init__.py
│   ├── dependencies.py         # get_tenant, require_admin, require_super_admin
│   ├── middleware/             # one file per middleware (access_log, rate_limit, ...)
│   │   ├── __init__.py         # re-exports each middleware class
│   │   └── access_log.py       # AccessLogMiddleware (request_id, ip, status, duration_ms)
│   ├── error_handler.py        # AppError → HTTP response mapping
│   └── routes/
│       ├── __init__.py
│       ├── health.py           # GET /health — no auth
│       ├── auth.py             # /api/v1/auth/*
│       ├── webhooks.py         # /api/v1/webhooks/whatsapp — no JWT auth
│       ├── companies.py        # /api/v1/companies/* — super_admin
│       ├── conversations.py    # /api/v1/conversations/*
│       ├── residents.py        # /api/v1/residents/*
│       └── contacts.py         # /api/v1/company-contacts/*
│
├── services/                   # LAYER 2: ORCHESTRATION
│   ├── __init__.py
│   ├── config_manager.py       # Postgres + Secrets Manager + Redis cache
│   ├── agent_service.py        # LangGraph agent orchestration
│   ├── conversation_service.py # Session lifecycle management
│   ├── profile_service.py      # Resident identification + verification
│   └── auth_service.py         # Login, token generation, refresh
│
├── domain/                     # LAYER 3: THE BRAIN
│   ├── __init__.py
│   ├── exceptions.py           # AppError base + all domain exceptions
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── company.py          # Company + CompanyConfig
│   │   ├── user.py             # User + Role enum
│   │   ├── resident.py         # Resident entity
│   │   ├── conversation.py     # Conversation + Status + ClosedReason
│   │   ├── config.py           # ResolvedConfig (secrets resolved)
│   │   └── contact.py          # CompanyContact + Section enum
│   └── agent/
│       ├── __init__.py
│       ├── graph.py            # LangGraph graph definition
│       ├── state.py            # TypedDict for agent state
│       ├── nodes.py            # Graph node functions
│       └── prompts.py          # System prompt templates
│
└── adapters/                   # LAYER 4: INFRASTRUCTURE
    ├── __init__.py
    ├── storage/
    │   ├── __init__.py
    │   ├── postgres/
    │   │   ├── __init__.py     # re-exports Base + every ORM class for Alembic
    │   │   ├── database.py     # DeclarativeBase, async engine, session factory
    │   │   ├── company/        # one folder per entity (model + repo together)
    │   │   │   ├── __init__.py
    │   │   │   ├── models.py        # CompanyORM
    │   │   │   └── repositories.py  # CompanyRepository
    │   │   ├── user/
    │   │   │   ├── __init__.py
    │   │   │   ├── models.py        # UserORM
    │   │   │   └── repositories.py  # UserRepository (incl. find_with_credentials)
    │   │   └── refresh_token/
    │   │       ├── __init__.py
    │   │       ├── models.py        # RefreshTokenORM
    │   │       └── repositories.py  # RefreshTokenRepository
    │   └── (every adapter is Postgres — Mongo was removed in 2026-04)
    │   │   ├── conversation/
    │   │   │   ├── models.py
    │   │   │   └── repositories.py
    │   │   ├── resident/
    │   │   │   ├── models.py
    │   │   │   └── repositories.py
    │   │   └── contact/
    │   │       ├── models.py
    │   │       └── repositories.py
    │   └── redis/
    │       ├── __init__.py
    │       ├── client.py       # Redis connection
    │       ├── config_cache.py # config:{company_id} cache ops
    │       ├── session_cache.py # session:{phone}:{company_id} cache ops
    │       └── rate_limiter.py # rate:{phone}:{company_id} counter
    ├── erp/
    │   ├── __init__.py
    │   ├── priority_client.py  # HTTP client for Priority ERP API
    │   └── mappers.py          # Priority response → domain entities
    ├── messaging/
    │   ├── __init__.py
    │   ├── whatsapp_client.py  # WhatsApp Cloud API (send/receive)
    │   └── templates.py        # WhatsApp message template definitions
    └── cloud/
        ├── __init__.py
        ├── s3_client.py        # Media upload/download
        └── secrets_client.py   # AWS Secrets Manager fetch
```

---

## Workers (planned — not yet created)

```
backend/app/
├── workers/
│   ├── __init__.py
│   └── tasks/
│       ├── __init__.py
│       ├── agent_task.py       # Queue: messages.whatsapp — handle incoming text
│       ├── media_task.py       # Queue: messages.media — download + S3 + trigger agent
│       ├── session_task.py     # Queue: messages.session — expiry + reminders (Beat)
│       └── priority_task.py    # Queue: messages.priority — Priority ERP bulk webhooks
```

> These files don't exist yet — the Celery worker + Beat containers are running
> with empty task lists. Tasks are added as features land (Phase 1 POC).

Workers live inside `backend/app/` because they import services and adapters. They are separate Docker containers but same codebase.

---

## Tests

```
backend/tests/
├── __init__.py
├── conftest.py                 # Shared fixtures (test client, test DB, etc.)
├── test_health.py              # Smoke test for /health
├── unit/                       # Domain layer — pure logic, no I/O
│   ├── __init__.py
│   ├── test_conversation.py
│   ├── test_resident.py
│   └── test_agent_nodes.py
├── integration/                # Adapters — real DB connections
│   ├── __init__.py
│   ├── test_config_repo.py
│   ├── test_resident_repo.py
│   └── test_priority_client.py
└── e2e/                        # Full flow — API → service → adapter
    ├── __init__.py
    ├── test_webhook_flow.py
    └── test_auth_flow.py
```

**Test naming:** `test_{module}.py` mirrors the source file it tests.

---

## Migrations

```
backend/migrations/
├── env.py                      # Alembic environment config
├── versions/                   # Auto-generated migration files
│   ├── 001_create_companies.py
│   ├── 002_create_users.py
│   └── 003_create_refresh_tokens.py
└── README
```

Postgres-only stack (every entity has an Alembic migration in `backend/migrations/versions/`).

---

## Scripts

```
backend/scripts/
├── seed_demo_companies.py      # Seed 4-5 demo companies for POC
├── create_super_admin.py       # Create first super_admin user
└── test_priority_connection.py # Verify Priority ERP connectivity
```

One-off operational scripts. Not imported by the app. Run directly: `python backend/scripts/seed_demo_companies.py`

---

## Key Files Explained

| File | Purpose |
|------|---------|
| `backend/app/main.py` | Creates FastAPI app, registers routers, sets up lifespan (startup/shutdown) |
| `backend/app/bootstrap.py` | Dependency injection — creates all adapters and services, wires them together |
| `backend/app/core/config.py` | Loads and validates all env vars via pydantic-settings |
| `backend/app/core/celery_app.py` | Celery instance with queue routing config |
| `backend/app/api/dependencies.py` | FastAPI `Depends()` — JWT extraction, tenant context, role guards |
| `backend/app/api/error_handler.py` | Global exception handler — domain errors → HTTP responses |
| `backend/app/domain/exceptions.py` | All custom exceptions (`CompanyNotFoundError`, `ResidentNotVerifiedError`, etc.) |
| `pyproject.toml` | Root — deps, ruff, pytest, hatchling (`packages = ["backend/app"]`) |
| `Makefile` | Root — `make up-dev / build-dev / rebuild-dev / restart-dev / stop-dev / logs-dev` |
| `docker-compose.dev.yml` | Root — local dev orchestration, uses `backend/Dockerfile` |
| `.pre-commit-config.yaml` | Root — ruff (+ auto-fix), gitleaks, basic hooks |
| `.github/workflows/ci.yml` | CI — ruff lint+format, pytest, gitleaks, pip-audit |

---

## Naming Conventions for Files

| Layer | File naming | Example |
|-------|------------|---------|
| Routes | `{resource}.py` | `conversations.py` |
| Services | `{context}_service.py` | `agent_service.py` |
| Domain entities | `{entity}.py` | `resident.py` |
| Adapters (repos) | `{entity}_repo.py` | `config_repo.py` |
| Adapters (clients) | `{service}_client.py` | `priority_client.py` |
| Workers | `{name}_task.py` | `agent_task.py` |
| Tests | `test_{module}.py` | `test_conversation.py` |

---

## What Goes Where — Quick Reference

| I need to... | Create/edit file in... |
|--------------|----------------------|
| Add a new API endpoint | `backend/app/api/routes/` |
| Add business logic | `backend/app/domain/` |
| Add a database query | `backend/app/adapters/storage/<db>/<entity>/repositories.py` |
| Add an external API call | `backend/app/adapters/erp/` or `backend/app/adapters/messaging/` |
| Add a background task | `backend/app/workers/tasks/` |
| Add a new Pydantic model | `backend/app/domain/entities/` |
| Add a new exception | `backend/app/domain/exceptions.py` |
| Add auth/role checks | `backend/app/api/dependencies.py` |
| Add a new env var | `backend/app/core/config.py` + `.env.example` + `.env.dev` + `docs/standards/env.md` |
| Add a Postgres migration | `backend/migrations/versions/` |
| Add a test | `backend/tests/` (mirroring source path) |
