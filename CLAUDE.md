# CLAUDE.md

## Project Overview

**DopaCRM** — a multi-tenant SaaS CRM built for gyms and fitness studios. Gym owners manage members, membership plans, revenue, and leads from one platform. Each gym is an isolated tenant configured via database records, not code changes. Built on a template from "Assets Agent" — infrastructure file names will be renamed over time.

## Architecture

- **Modular Monolith** — single codebase, internal separation by service module
- **Queue-first** — FastAPI only receives/validates, background work goes to Celery workers via RabbitMQ
- **Config-driven tenancy** — new gym = new tenant record + config
- **4-Layer Hexagonal** — API → Services → Domain ← Adapters. Domain is pure, imports nothing.

## Stack

- **API:** FastAPI (with JWT auth via PyJWT, HTTPBearer)
- **Queue:** RabbitMQ + Celery workers
- **Databases:** PostgreSQL (tenants, users, members, plans, subscriptions, payments, leads), MongoDB (config, activity logs, audit), Redis (cache, rate limits)
- **Auth:** argon2 password hashing, JWT access tokens (HS256, 8h expiry)
- **Frontend:** React + TypeScript + Vite dashboard (Phase 2)
- **Infrastructure:** Docker Compose (dev), AWS (prod)
- **Observability:** structlog (JSON), Loki + Promtail (logs), Grafana (dashboards), Sentry, Flower, CloudWatch

## Key Patterns

- Every request is scoped by `tenant_id` (company_id in code) — extracted from JWT via `get_current_user` dependency
- Routes are **thin** — parse HTTP, call service, format response. No business logic.
- Services are **smart** — permission checks, company scoping, orchestration.
- Domain is **pure** — Pydantic entities + business rules. Zero external dependencies.
- Adapters are **isolated** — repos translate ORM ↔ domain entities at the boundary.
- Failed tasks go to dead letter queue — never silently disappear
- Postgres is the **default** database for transactional entities. MongoDB holds tenant config (feature flags, limits, plan settings) and document-shaped data. Flexibility within Postgres entities uses **JSONB columns** (`plans.custom_attrs`, `members.custom_fields`).

## Data Split

- **PostgreSQL:** `tenants`, `users`, `saas_plans`, `members`, `membership_plans`, `subscriptions`, `payments`, `leads`, `refresh_tokens` — plus JSONB columns for per-tenant config, per-plan custom attributes, per-member custom fields
- **MongoDB:** `tenant_configs` (feature flags, limits, settings per gym), `activity_logs`, `audit_trails`, `lead_activities`, `integration_payloads`
- **Redis:** config cache, session cache, rate limits, quotas

## Roles

- `super_admin` — platform level, `tenant_id = null`, onboards gyms, creates first users
- `owner` — full tenant access, billing, configuration
- `staff` — day-to-day operations (check-in, payments, member management)
- `sales` — lead pipeline, trials, conversions

## Project Structure — 4-Layer Hexagonal

```
dopacrm/                         # Repository root
├── pyproject.toml               # Python project (deps, ruff, pytest, hatchling)
├── Makefile                     # make up-dev / build-dev / migrate-up-dev / ...
├── docker-compose.dev.yml       # Local dev (12 containers, t3.medium resource limits)
├── alembic.ini                  # Alembic config (Postgres migrations)
├── .env.example                 # Env var template (committed)
├── .env.dev                     # Local dev env (gitignored)
├── .pre-commit-config.yaml      # ruff + gitleaks + basic hooks
├── .github/workflows/ci.yml     # ruff, pytest, gitleaks, pip-audit, docker-build
├── docker/                      # Compose-mounted configs (Loki, Promtail, Grafana)
│
└── backend/
    ├── Dockerfile               # python:3.13-slim + uv, non-root user
    ├── app/                     # Importable as `app.*` (NOT `backend.app.*`)
    │   ├── main.py              # FastAPI entry, registers v1 router + error handler
    │   ├── core/                # config.py, security.py (JWT + argon2), logger.py, time.py, celery_app.py
    │   ├── api/                 # LAYER 1: routes, dependencies, middleware, error_handler
    │   │   ├── dependencies/    # auth.py (JWT → TokenPayload), database.py (get_session)
    │   │   ├── middleware/      # access_log.py (structured request logging)
    │   │   ├── error_handler.py # Global AppError → HTTP mapping
    │   │   └── v1/              # Versioned API — feature folders
    │   │       ├── router.py    # Central v1 router
    │   │       ├── auth/        # router.py + schemas.py (login, me)
    │   │       └── users/       # router.py + schemas.py (CRUD + list)
    │   ├── services/            # LAYER 2: user_service.py, auth_service.py, ...
    │   ├── domain/              # LAYER 3: entities/ (user.py, company.py, ...), exceptions.py
    │   └── adapters/            # LAYER 4: storage/postgres/<entity>/{models.py, repositories.py}
    ├── tests/                   # 12 tests (health, auth_service, user_entity)
    ├── migrations/              # Alembic (0001_create_users_companies_tokens)
    └── scripts/                 # create_super_admin.py
```

**Package import path:** `from app.domain.entities.user import User`, never `from backend.app...`.

**Dependency rule:** `api → services → domain ← adapters`. Domain never imports from adapters or api. Routes never import repositories directly — always go through a service.

## API Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/api/v1/auth/login` | None | Email + password → JWT token |
| GET | `/api/v1/auth/me` | Bearer | Current user profile |
| POST | `/api/v1/users` | super_admin | Create user |
| GET | `/api/v1/users` | Bearer | List users (company-scoped) |
| GET | `/api/v1/users/{id}` | Bearer | Get user |
| PATCH | `/api/v1/users/{id}` | admin+ | Update user |
| DELETE | `/api/v1/users/{id}` | admin+ | Soft-delete (is_active=false) |

## Current Phase

Early development — building the core platform: tenants, users, members, plans, revenue, leads, dashboard.

## Documentation

- Product spec: `docs/specs.md`
- Standards: `docs/standards/` (python, architecture, git, env, project-structure, feature-docs)
- 4-layer guide: `docs/standards/4-layer-example-users.md`
- Feature docs: `docs/features/` (per-feature implementation specs)
