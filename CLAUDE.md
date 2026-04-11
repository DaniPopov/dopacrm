# CLAUDE.md

## Project Overview

**DopaCRM** — a multi-tenant SaaS CRM built for gyms and fitness studios. Gym owners manage members, membership plans, revenue, and leads from one platform. Each gym is an isolated tenant configured via database records, not code changes. Built on a template from "Assets Agent" — infrastructure file names will be renamed over time.

## Architecture

- **Modular Monolith** — single codebase, internal separation by service module
- **Queue-first** — FastAPI only receives/validates, background work goes to Celery workers via RabbitMQ
- **Config-driven tenancy** — new gym = new tenant record + config
- **4-Layer Hexagonal** — API → Services → Domain ← Adapters. Domain is pure, imports nothing.

## Stack

- **API:** FastAPI (Python 3.13+, async) with JWT via PyJWT
- **Queue:** RabbitMQ + Celery workers
- **Databases:** PostgreSQL (transactional entities), MongoDB (config, activity logs, audit), Redis (cache, rate limits, token blacklist)
- **Auth:** argon2 password hashing, JWT access tokens (HS256, 8h) stored in HttpOnly cookie. Logout blacklists the token's jti in Redis. Dual support — cookie (frontend) + Bearer header (Swagger/API clients).
- **Storage:** AWS S3 for logos and uploads. Env-based folder prefixes (`dev/`, `staging/`, `prod/`). Private bucket, served via presigned URLs.
- **Frontend:** React 19 + TypeScript + Vite + TanStack Query + shadcn/ui, Hebrew RTL, feature-based architecture
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
| POST | `/api/v1/auth/login` | None | Email + password → HttpOnly cookie + JWT in body (10/min/IP) |
| POST | `/api/v1/auth/logout` | Cookie/Bearer | Clears cookie + blacklists token in Redis |
| GET | `/api/v1/auth/me` | Cookie/Bearer | Current user profile |
| POST | `/api/v1/tenants` | super_admin | Onboard a gym (auto: default plan, 14-day trial) |
| GET | `/api/v1/tenants` | super_admin | List all gyms |
| GET | `/api/v1/tenants/{id}` | Bearer | Get tenant (includes logo_presigned_url) |
| PATCH | `/api/v1/tenants/{id}` | super_admin | Update tenant fields |
| POST | `/api/v1/tenants/{id}/suspend` | super_admin | Suspend |
| POST | `/api/v1/tenants/{id}/activate` | super_admin | Reactivate |
| POST | `/api/v1/tenants/{id}/cancel` | super_admin | Soft delete (status=cancelled) |
| POST | `/api/v1/uploads/logo` | super_admin | Multipart logo upload to S3 → { key, presigned_url } |
| POST | `/api/v1/users` | super_admin | Create user |
| GET | `/api/v1/users` | Bearer | List users (tenant-scoped) |
| GET | `/api/v1/users/{id}` | Bearer | Get user |
| PATCH | `/api/v1/users/{id}` | owner+ | Update user |
| DELETE | `/api/v1/users/{id}` | owner+ | Soft-delete (is_active=false) |

All authenticated endpoints pass through `api_rate_limit` (60/min/user). Login has its own stricter `login_rate_limit` (10/min/IP).

## Frontend conventions (quick reference)

- **Feature-based** — each feature (`auth`, `tenants`, `dashboard`, `landing`) has its own folder with `api.ts`, `hooks.ts`, `types.ts`, pages, and tests co-located.
- **Error handling** — all HTTP errors become `ApiError` (with `status`). Pages use humanizer functions from `lib/api-errors.ts` (`humanizeLoginError`, `humanizeTenantError`, `humanizeUploadError`) to translate to Hebrew user-facing messages. Never show raw backend `detail` strings to users.
- **TanStack Query** — every `api.ts` function is wrapped in a hook (`useTenants`, `useCreateTenant`, etc.). Mutations `invalidateQueries` on success to refresh lists automatically.
- **Shared form components** — `TenantForm` is used by both "Create" card and "Edit" dialog. Reuse > duplicate.
- **Row actions** — tables use a "פעולות" dropdown per row with role-gated actions (Edit, Activate, Suspend, Cancel). Destructive actions (Cancel) open a `ConfirmDialog`.
- **Images** — all static images in `frontend/public/`, referenced as URL strings (`"/dopa-icon.png"`). No module imports.

See `docs/frontend.md` for the full architecture guide.

## Current Phase

Early development — building the core platform: tenants, users, members, plans, revenue, leads, dashboard.

## Documentation

- Product spec: `docs/specs.md`
- Backend architecture: `docs/backend.md`
- Frontend architecture: `docs/frontend.md`
- Standards: `docs/standards/` (python, architecture, git, env, project-structure, feature-docs)
- 4-layer guide: `docs/standards/4-layer-example-users.md`
- Feature docs: `docs/features/` (users, auth, tenants, saas-plans, per-feature implementation specs)
- **How-to skills:** `docs/skills/` — step-by-step recipes for building new features (frontend and backend)
