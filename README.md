# DopaCRM

Multi-tenant SaaS CRM built for gyms and fitness studios. Manage members, track revenue per member, nurture leads, and run daily operations — all from one platform designed around how gyms actually work. One codebase, one deployment, infinite tenants.

**Core thesis:** most gym CRMs are rigid — you take what the vendor built. DopaCRM is the **most flexible** one — gym owners customize roles, fields, workflows, and dashboards to fit how their specific gym actually operates. See [`docs/spec.md`](docs/spec.md) §1.

## What It Does

- **Member management** — profiles, plans, statuses (active / frozen / cancelled), join dates, notes, custom fields
- **Membership plans** — recurring (monthly, quarterly, annual) and one-off (drop-ins, trial passes)
- **Classes + class passes + attendance** — punch cards, unlimited passes, check-in flow, low-entries dashboard
- **Revenue tracking** — income per member, per plan, per month. Month-over-month view
- **Lead pipeline** — capture, assign, track through stages (new → contacted → trial → converted / lost)
- **Owner-configurable roles** — only `super_admin` and `owner` are system; everything else is per-tenant
- **Multi-tenant** — every gym is isolated by config + JWT-scoped queries
- **Queue-first architecture** — FastAPI receives and validates, all real work goes to Celery workers via RabbitMQ

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (Python 3.13) |
| Task Queue | RabbitMQ + Celery |
| Databases | MongoDB (config, activity logs) + PostgreSQL (tenants, users, members, plans, payments) + Redis (cache, rate limits, JWT blacklist) |
| Frontend | React 19 + TypeScript + Vite + TanStack Query + shadcn/ui |
| Type sharing | OpenAPI codegen (FastAPI → `openapi-typescript` → frontend types) — no hand-written DTOs |
| Storage | AWS S3 (logos, uploads) — env-based folder prefixes |
| Auth | JWT (HS256, 8h) in HttpOnly cookie + Redis jti blacklist on logout |
| Infrastructure | Docker Compose (dev), AWS (prod) |
| Logging | structlog (JSON) → Loki + Promtail → Grafana |
| Observability | Sentry (errors), Flower (Celery), CloudWatch |

## Architecture

Modular monolith with **4-layer hexagonal architecture** — one codebase with clean internal separation. Not microservices.

- Routes are **thin** — parse HTTP, call service, return response. No business logic.
- Services are **smart** — permission checks, tenant scoping, orchestration.
- Domain is **pure** — entities + business rules. Zero external dependencies.
- Adapters are **isolated** — repos translate ORM ↔ domain entities at the boundary.

## Phase status

- **Phase 1 — Foundation** ✅ Tenants, Users, Auth, S3 logos, Hebrew dashboard shell, role-based sidebar, central permissions module, route guards, rate limiting
- **Phase 2 — Core CRM** 🚧 Members (next), Membership Plans, Subscriptions, Payments, Classes + Passes + Attendance, Leads
- **Phase 4 — Flexibility** 📋 Dynamic roles (`tenant_roles` table), owner settings UI, custom field definitions, configurable dashboards

## Docs

- [Product Spec](docs/spec.md) — features, domain model, roles, data architecture, flexibility thesis
- [Backend Architecture](docs/backend.md) — Python/FastAPI, 4-layer design, request flow, testing
- [Frontend Architecture](docs/frontend.md) — React/TypeScript, feature-based structure, TanStack Query, OpenAPI codegen, every API function documented
- [Standards](docs/standards/) — coding conventions (Python, architecture, Git, feature docs)
- [Features](docs/features/) — per-feature implementation specs:
  - Shipped: [auth](docs/features/auth.md), [tenants](docs/features/tenants.md), [users](docs/features/users.md), [saas-plans](docs/features/saas-plans.md)
  - Planned: [members](docs/features/members.md), [classes + passes + attendance](docs/features/classes.md), [roles](docs/features/roles.md)
- [Mobile setup plan](docs/mobile-setup.md) — React Native + Expo plan, deferred until after web CRM ships to prod
- [Skills](docs/skills/) — step-by-step recipes for building new [frontend](docs/skills/build-frontend-feature.md) / [backend](docs/skills/build-backend-feature.md) features

## Prerequisites

- **Docker Desktop** — [download](https://www.docker.com/products/docker-desktop/)
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Make** — pre-installed on macOS / Linux
- **TablePlus** (optional) — [download](https://tableplus.com) — GUI for Postgres, MongoDB, Redis

## Setup (first time)

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd dopacrm

# 2. Install Python dependencies
uv sync

# 3. Copy env template and fill in values
cp .env.example .env.dev
# Edit .env.dev with your real values (MongoDB, AWS, Langfuse, etc.)

# 4. Build the backend image
make build-dev

# 5. Start the full dev stack (12 containers)
make up-dev
# First run pulls ~1.5 GB of images (mongo, postgres, redis, rabbitmq, etc.)
# Healthchecks ensure services start in the right order (~30s)

# 6. Apply database migrations (creates tenants, users, saas_plans, refresh_tokens, ...)
make migrate-up-dev

# 7. Create the platform super_admin user
SEED_EMAIL=your@email.com SEED_PASSWORD=your-password make seed-super-admin-dev

# 8. Verify everything works
curl http://localhost:8000/health
# → {"status":"ok"}

# 9. See all service URLs
make urls-dev
```

## Daily workflow

```bash
# Start everything
make up-dev

# Work on code — backend auto-reloads on save (uvicorn --reload)

# Check logs
make logs-backend-dev      # just the backend
make logs-worker-dev       # just the celery worker
make logs-dev              # everything (noisy)

# Stop when done
make stop-dev              # pause (containers preserved, fast resume)
make down-dev              # full stop (containers removed, volumes kept)
```

## Service URLs

After `make up-dev`, these are available:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Backend API** | http://localhost:8000 | — |
| **Swagger docs** | http://localhost:8000/docs | — |
| **ReDoc** | http://localhost:8000/redoc | — |
| **Mongo Express** | http://localhost:8081 | no auth in dev |
| **RabbitMQ Management** | http://localhost:15672 | `guest` / `guest` |
| **Flower (Celery UI)** | http://localhost:5555 | no auth in dev |
| **Grafana** | http://localhost:3000 | anonymous admin |

Run `make urls-dev` to see this list with raw connection ports.

## Connecting with TablePlus

[TablePlus](https://tableplus.com) can connect to Postgres, MongoDB, and Redis from one app.

### Postgres

| Field | Value |
|-------|-------|
| Host | `127.0.0.1` |
| Port | `5432` |
| User | `dopacrm` |
| Password | `dopacrm` |
| Database | `dopacrm` |
| SSL mode | PREFERRED |

After `make migrate-up-dev` you'll see: `tenants`, `users`, `saas_plans`, `refresh_tokens`, `alembic_version`.

### MongoDB

| Field | Value |
|-------|-------|
| Host | `127.0.0.1` |
| Port | `27017` |
| User | `root` |
| Password | `root` |
| Auth Database | `admin` |

Or use **Mongo Express** at http://localhost:8081 for a web UI.

### Redis

| Field | Value |
|-------|-------|
| Host | `127.0.0.1` |
| Port | `6379` |
| Password | *(empty)* |
| Database | `0` |

## Dashboards guide

### Grafana (logs) — http://localhost:3000

Grafana queries Loki for structured logs from all containers.

1. Open http://localhost:3000
2. Click **Explore** (compass icon, left sidebar)
3. Select **Loki** datasource
4. Try these queries:

```logql
# All backend logs
{container="dopacrm-backend"}

# Only completed requests
{container="dopacrm-backend"} | json | event="request_completed"

# Errors from any service
{project="dopacrm"} | json | level="error"

# Slow requests (>100ms)
{container="dopacrm-backend"} | json | http_duration_ms > 100
```

### RabbitMQ Management — http://localhost:15672

Login: `guest` / `guest`

| Tab | What to check |
|-----|---------------|
| **Queues** | Message depth per queue. `Ready > 0` for a long time = workers can't keep up. |
| **Connections** | Which containers are connected (backend, worker, flower). |
| **Overview** | Publish/deliver rates. Should be near-zero when idle. |

### Flower (Celery) — http://localhost:5555

| Tab | What to check |
|-----|---------------|
| **Tasks** | History of every task — state, args, duration, traceback on failure. |
| **Workers** | Which workers are online, what queues they listen on. |
| **Dashboard** | Active/succeeded/failed counters, task rate chart. |

### Mongo Express — http://localhost:8081

Web UI for browsing MongoDB collections. Click a database name → click a collection → see documents. Useful for inspecting tenant configs and conversation data.

## Make Targets

Run `make` for the full sectioned list. Summary:

| Section | Targets |
|---------|---------|
| **Stack** | `up-dev`, `build-dev`, `rebuild-dev`, `restart-dev`, `stop-dev`, `down-dev` |
| **Per-service** | `<action>-<svc>-dev` — pattern rule for actions (`up`/`stop`/`restart`/`build`/`rebuild`/`logs`) on any service. Examples: `make restart-backend-dev`, `make logs-frontend-dev`, `make stop-postgres-dev`, `make rebuild-frontend-dev` |
| **API types** | `gen-api-types`, `check-api-types` — regenerate / verify frontend TypeScript types from backend OpenAPI |
| **Database** | `migrate-up-dev`, `migrate-down-dev`, `migrate-status-dev`, `migrate-history-dev`, `seed-super-admin-dev`, `list-tables-dev`, `clean-database-dev` |
| **Logs** | `logs-dev` (all services), `logs-<service>-dev` (per service via pattern rule) |
| **Testing** | `test-backend-unit`, `test-backend-integration-dev`, `test-backend-e2e-dev`, `test-backend-all-dev`, `test-frontend`, `test-all-dev` |
| **Load testing** | `load-test-auth`, `load-test-users`, `load-test-tenants` |
| **Info** | `list-services-dev`, `status-dev`, `urls-dev` |

### Cleaning the database

During development you often want to wipe test data without resetting the whole stack.

```bash
# See what tables exist
make list-tables-dev

# Truncate a single table (all rows removed, schema preserved)
make clean-database-dev TABLE=tenants
make clean-database-dev TABLE=users

# Truncate ALL user data at once
# Preserved: saas_plans (reference data) + alembic_version (migration history)
make clean-database-dev TABLE=all
```

**What's preserved:**
- `saas_plans` — seeded by migration `0003`, don't wipe it (tenants FK into it)
- `alembic_version` — Alembic migration history

**Full nuclear reset** (drops schema + volume, re-runs migrations):
```bash
make down-dev
docker volume rm dopacrm_postgres-data
make up-dev
make migrate-up-dev
```

## Project Layout

- `backend/app/` — Application code (4-layer hexagonal, importable as `app`)
- `backend/tests/` — Tests (pytest, 89+ tests across unit/integration/e2e)
- `backend/scripts/` — `create_super_admin.py`, `export_openapi.py` (for type drift CI)
- `backend/migrations/` — Alembic migrations (Postgres)
- `backend/Dockerfile` — Backend image (python:3.13-slim + uv, non-root)
- `frontend/src/` — React app (feature-based, 77 tests)
- `frontend/src/lib/api-schema.ts` — **auto-generated** from backend OpenAPI (do not edit)
- `frontend/src/lib/api-types.ts` — clean type aliases consumed by feature code
- `docker/` — Loki, Promtail, Grafana config files (compose-mounted)
- `pyproject.toml` — Python project config (root)
- `docker-compose.dev.yml` — Local dev orchestration (12 containers)
- `docs/` — Architecture, standards, per-feature specs
- `.github/workflows/ci.yml` — CI: ruff, pytest, gitleaks, pip-audit, npm audit, OpenAPI drift, docker-build
- `.pre-commit-config.yaml` — Pre-commit hooks

## Load Testing (Locust)

[Locust](https://locust.io) runs from your Mac against the dev stack. Each scenario is a standalone file in `loadtests/`.

### Quick start

```bash
# Make sure the dev stack is running
make up-dev

# Run a load test (opens web UI at http://localhost:8089)
make load-test-auth     # hammers /login — validates rate limiting
make load-test-users    # simulates dashboard users — tests DB + API
```

### Using the Locust web UI (http://localhost:8089)

1. **Number of users** — how many simulated users to run concurrently (start with 5-10)
2. **Ramp up** — how many users to add per second (start with 1-2)
3. Click **Start** → watch the live charts

### What to look at

| Tab | What it shows |
|-----|---------------|
| **Statistics** | Requests/sec, average/median/p95 response times, failure rate |
| **Charts** | Live graphs of response times and requests/sec over time |
| **Failures** | Which requests failed and why (429 = rate limit, 500 = server error) |
| **Download Data** | Export results as CSV for reporting |

### What the numbers mean

| Metric | Healthy | Investigate |
|--------|---------|-------------|
| **p95 response time** | < 200ms | > 500ms |
| **Failure rate** | 0% (or only 429s from rate limiting) | Any 500s |
| **Requests/sec** | Stable | Dropping over time (= resource exhaustion) |

### Available scenarios

| Command | File | What it tests |
|---------|------|---------------|
| `make load-test-auth` | `loadtests/test_auth_load.py` | Login rate limiting — should see 429s after 10 req/min/IP |
| `make load-test-users` | `loadtests/test_users_load.py` | Authenticated CRUD — list users (5x), profile (3x), health (1x) |
| `make load-test-tenants` | `loadtests/test_tenants_load.py` | Tenant CRUD as super_admin — list, get, create |

### Headless mode (no UI, for CI)

```bash
uv run locust -f loadtests/test_users_load.py \
    --host=http://localhost:8000 \
    --headless -u 20 -r 5 -t 30s
```

`-u 20` = 20 users, `-r 5` = ramp 5/sec, `-t 30s` = run for 30 seconds.

## Type sharing — backend ↔ frontend

The frontend never hand-writes API types. They're generated from FastAPI's `/openapi.json`:

```bash
make gen-api-types       # regenerate frontend/src/lib/api-schema.ts
make check-api-types     # CI gate — fails if committed types drift from backend
```

`frontend/src/lib/api-types.ts` re-exports the generated types with friendly aliases (`Tenant`, `User`, `CreateTenantRequest`, etc.). Feature code imports from there and stays untouched when the underlying schema regenerates.

When mobile lands (React Native), it consumes the same generated types via a shared package — same flow, same source of truth.

## Dev Tools

- **Backend package manager:** [uv](https://github.com/astral-sh/uv) (Astral)
- **Linter / formatter:** [ruff](https://github.com/astral-sh/ruff) (handles import sorting via the `I` rule — no separate isort needed)
- **Backend tests:** pytest + pytest-asyncio
- **Frontend tests:** Vitest + Testing Library + jsdom
- **Load testing:** [Locust](https://locust.io) — `loadtests/` directory
- **Type codegen:** [openapi-typescript](https://openapi-ts.dev) — frontend types from FastAPI OpenAPI
- **Pre-commit:** ruff (+ auto-fix), gitleaks, basic hygiene hooks
- **CI:** GitHub Actions — ruff, pytest, frontend lint+test, OpenAPI type drift, gitleaks, pip-audit, npm audit, docker-build

## Troubleshooting

### Port conflict on 5432 (Postgres)

If you have a local Postgres installed via Homebrew, it fights with Docker's Postgres over port 5432:

```bash
# Check what's on port 5432
lsof -i :5432

# Stop and uninstall local Postgres
brew services stop postgresql@14
brew services stop postgresql@15
brew uninstall postgresql@14 postgresql@15
```

### Orphan containers warning

If you see "Found orphan containers", run:

```bash
make down-dev
make up-dev    # --remove-orphans is built into this target
```

### Postgres "role does not exist"

Postgres only creates the user on first init. If the volume existed before the current env vars:

```bash
make down-dev
docker volume rm dopacrm_postgres-data
make up-dev
make migrate-up-dev
```

### Mongo healthcheck noise

Mongo logs connection metadata on every healthcheck. We use `--quiet` + 30s interval to minimize this. Some noise is expected — use `make logs-backend-dev` instead of `make logs-dev` to filter it out.
