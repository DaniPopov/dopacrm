# DopaCRM

Multi-tenant SaaS CRM built for gyms and fitness studios. Manage members, track revenue per member, nurture leads, and run daily operations — all from one platform designed around how gyms actually work. One codebase, one deployment, infinite tenants.

## What It Does

- **Member management** — profiles, plans, statuses (active / frozen / cancelled), join dates, notes
- **Membership plans** — recurring (monthly, quarterly, annual) and one-off (drop-ins, trial passes)
- **Revenue tracking** — income per member, per plan, per month. Month-over-month view
- **Lead pipeline** — capture, assign, track through stages (new → contacted → trial → converted / lost)
- **Multi-tenant** — every gym is isolated by config, not by code. New gym = new config document, not a new deployment
- **Queue-first architecture** — FastAPI receives and validates, all real work goes to Celery workers via RabbitMQ

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI |
| Task Queue | RabbitMQ + Celery |
| Databases | MongoDB (config, activity logs) + PostgreSQL (tenants, users, members, plans, payments) + Redis (cache, rate limits) |
| Frontend | React + TypeScript + Vite (dashboard) |
| Infrastructure | Docker Compose (dev), AWS (prod) |
| Logging | structlog (JSON) → Loki + Promtail → Grafana |
| Observability | Sentry (errors), Flower (Celery), CloudWatch |

## Architecture

Modular monolith with **4-layer hexagonal architecture** — one codebase with clean internal separation. Not microservices.

- Routes are **thin** — parse HTTP, call service, return response. No business logic.
- Services are **smart** — permission checks, tenant scoping, orchestration.
- Domain is **pure** — entities + business rules. Zero external dependencies.
- Adapters are **isolated** — repos translate ORM ↔ domain entities at the boundary.

## Docs

- [Product Spec](docs/spec.md) — features, domain model, roles, data architecture
- [Backend Architecture](docs/backend.md) — Python/FastAPI, 4-layer design, request flow, testing
- [Frontend Architecture](docs/frontend.md) — React/TypeScript, feature-based structure, TanStack Query
- [Standards](docs/standards/) — coding conventions (Python, architecture, Git, feature docs)

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

# 6. Apply database migrations (creates companies, users, refresh_tokens tables)
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

After `make migrate-up-dev` you'll see: `companies`, `users`, `refresh_tokens`, `alembic_version`.

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
| **Database** | `migrate-up-dev`, `migrate-down-dev`, `migrate-status-dev`, `migrate-history-dev`, `seed-super-admin-dev`, `list-tables-dev`, `clean-database-dev` |
| **Logs** | `logs-dev`, `logs-<service>-dev` (backend, worker, worker-beat, mongo, postgres, redis, rabbitmq, flower, grafana, loki, promtail, mongo-express) |
| **Testing** | `test-backend-unit`, `test-backend-integration-dev`, `test-backend-e2e-dev`, `test-backend-all-dev`, `test-frontend`, `test-all-dev` |
| **Info** | `urls-dev` |

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
- `backend/tests/` — Tests (pytest)
- `backend/scripts/` — Seed scripts (`create_super_admin.py`)
- `backend/migrations/` — Alembic migrations (Postgres)
- `backend/Dockerfile` — Backend image (python:3.13-slim + uv)
- `docker/` — Loki, Promtail, Grafana config files (compose-mounted)
- `pyproject.toml` — Python project config (root)
- `docker-compose.dev.yml` — Local dev orchestration (12 containers)
- `docs/` — Architecture, standards, full Notion spec
- `.github/workflows/ci.yml` — CI: ruff, pytest, gitleaks, pip-audit, docker-build
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

### Headless mode (no UI, for CI)

```bash
uv run locust -f loadtests/test_users_load.py \
    --host=http://localhost:8000 \
    --headless -u 20 -r 5 -t 30s
```

`-u 20` = 20 users, `-r 5` = ramp 5/sec, `-t 30s` = run for 30 seconds.

## Dev Tools

- **Package manager:** [uv](https://github.com/astral-sh/uv) (Astral)
- **Linter / formatter:** [ruff](https://github.com/astral-sh/ruff) (handles import sorting via the `I` rule — no separate isort needed)
- **Tests:** pytest + pytest-asyncio
- **Load testing:** [Locust](https://locust.io) — `loadtests/` directory
- **Pre-commit:** ruff (+ auto-fix), gitleaks, basic hygiene hooks
- **CI:** GitHub Actions — ruff, pytest, gitleaks, pip-audit, docker-build

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
