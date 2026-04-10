# DopaCRM — Backend Architecture

> Deep dive into the Python/FastAPI backend. For the product spec see [`specs.md`](./specs.md). For coding standards see [`standards/`](./standards/).

---

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13+ |
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.x (async) |
| Primary DB | PostgreSQL 17 |
| Secondary DB | MongoDB 7 (config, activity logs) |
| Cache | Redis 7 |
| Queue | RabbitMQ + Celery |
| Migrations | Alembic |
| Auth | argon2 (passwords) + PyJWT (HS256 tokens) |
| Logging | structlog → Loki → Grafana |
| Package manager | uv |
| Linter/formatter | ruff |
| Type checker | mypy |
| Tests | pytest + pytest-asyncio |
| Load tests | Locust |

---

## 4-Layer Hexagonal Architecture

```
┌──────────────────────────────────────────────┐
│  Layer 1 — API        (FastAPI routers)      │  HTTP in, HTTP out
├──────────────────────────────────────────────┤
│  Layer 2 — Services   (use cases)            │  Business rules, orchestration
├──────────────────────────────────────────────┤
│  Layer 3 — Domain     (entities, rules)      │  Pure Python, no I/O
├──────────────────────────────────────────────┤
│  Layer 4 — Adapters   (repos, DB)            │  Postgres / Mongo behind interfaces
└──────────────────────────────────────────────┘
```

### Dependency rule

`API → Services → Domain ← Adapters`

- Domain imports nothing. No FastAPI, no SQLAlchemy, no Mongo.
- Services import Domain + Repository interfaces. Never import FastAPI or ORM.
- API imports Services + Pydantic schemas. Never imports repositories.
- Adapters import Domain entities (to map to/from ORM). Never import services or API.

### Layer responsibilities

| Layer | Knows about | Responsible for |
|-------|-------------|-----------------|
| **API** | FastAPI, Pydantic request/response schemas, dependencies | Parse HTTP, validate input, call service, format response |
| **Service** | Domain entities, repository interfaces, `TokenPayload` | Permission checks, business rules, transaction management (`commit`) |
| **Domain** | Standard library only, Pydantic BaseModel | Entities, value objects, enums, pure business logic, custom exceptions |
| **Adapter** | SQLAlchemy ORM, MongoDB driver, domain entities | Translate ORM ↔ domain entities, SQL queries, handle `IntegrityError` |

---

## Folder Structure

```
backend/
├── app/
│   ├── main.py                         # FastAPI app + middleware
│   ├── core/                           # Cross-cutting concerns
│   │   ├── config.py                   # Pydantic Settings (env vars)
│   │   ├── security.py                 # argon2 + JWT (stateless)
│   │   ├── logger.py                   # structlog setup
│   │   ├── time.py                     # System tz (Israel) + UTC + tenant tz
│   │   └── celery_app.py              # Celery config
│   │
│   ├── api/                            # LAYER 1
│   │   ├── dependencies/               # FastAPI Depends (auth, DB session, rate limit)
│   │   ├── middleware/                  # Access logging
│   │   ├── error_handler.py            # AppError → HTTP status mapping
│   │   └── v1/                         # Versioned routes
│   │       ├── router.py               # Central v1 router
│   │       ├── auth/                   # login, me
│   │       ├── users/                  # CRUD
│   │       └── tenants/                # CRUD + suspend
│   │
│   ├── services/                       # LAYER 2
│   │   ├── user_service.py
│   │   └── tenant_service.py
│   │
│   ├── domain/                         # LAYER 3
│   │   ├── entities/                   # Pydantic models (User, Tenant, etc.)
│   │   └── exceptions.py              # AppError hierarchy
│   │
│   └── adapters/                       # LAYER 4
│       └── storage/
│           ├── postgres/
│           │   ├── database.py         # Engine + session factory
│           │   ├── tenant/             # models.py + repositories.py
│           │   ├── user/               # models.py + repositories.py
│           │   └── refresh_token/      # models.py + repositories.py
│           └── redis/
│               └── client.py           # Async Redis singleton
│
├── tests/
│   ├── unit/                           # Pure logic, no I/O
│   ├── integration/                    # Real Postgres
│   └── e2e/                            # Full HTTP with TestClient
│
├── migrations/                         # Alembic
└── scripts/                            # Seed scripts
```

---

## How a request flows

Example: `POST /api/v1/tenants` (create a gym)

```
1. HTTP request arrives at FastAPI

2. LAYER 1 — API router (api/v1/tenants/router.py)
   ├── FastAPI parses body → CreateTenantRequest (Pydantic)
   ├── Depends(require_super_admin) → validates JWT, checks role
   ├── Depends(get_session) → provides AsyncSession
   └── Calls service.create_tenant(caller=..., slug=..., name=...)

3. LAYER 2 — Service (services/tenant_service.py)
   ├── Checks caller.role == "super_admin" → raises InsufficientPermissionsError if not
   ├── Calls self._repo.create(slug=..., name=..., ...)
   ├── Calls self._session.commit()
   └── Returns Tenant (domain entity)

4. LAYER 4 — Repository (adapters/storage/postgres/tenant/repositories.py)
   ├── Creates TenantORM instance
   ├── session.add(orm) + flush()
   ├── Catches IntegrityError → raises TenantAlreadyExistsError
   ├── _to_domain(orm) → converts ORM row to Tenant (Pydantic)
   └── Returns Tenant

5. LAYER 3 — Domain (domain/entities/tenant.py)
   └── Tenant is a pure Pydantic model — no behavior here for create,
       but is_active(), TenantStatus enum, etc. are available

6. Back in LAYER 1 — API router
   ├── _to_response(tenant) → TenantResponse (Pydantic)
   └── Returns HTTP 201 + JSON body
```

---

## Error handling

All errors flow through domain exceptions → API error handler:

```
Repository raises TenantAlreadyExistsError
  → Service catches, wraps as AppError("...", "TENANT_SLUG_TAKEN")
    → API error_handler maps "TENANT_SLUG_TAKEN" → HTTP 409
      → JSON: {"error": "TENANT_SLUG_TAKEN", "detail": "..."}
```

Services and repositories **never** raise `HTTPException`. Only the API layer knows about HTTP.

---

## Auth flow

1. `POST /auth/login` — email + password → argon2 verify → JWT created (HS256, 8h expiry)
2. JWT payload: `{ sub: user_id, role: "super_admin", tenant_id: null }`
3. Every protected route uses `Depends(get_current_user)` → decodes JWT → returns `TokenPayload`
4. Role gates: `require_super_admin`, `require_owner`, `require_staff` — FastAPI dependencies

---

## Multi-tenancy

- Shared schema: every table has `tenant_id` column
- JWT carries `tenant_id` — extracted by `get_current_user`
- Services scope all queries through `tenant_id`
- `super_admin` has `tenant_id = null` and can access everything

---

## Testing strategy

| Tier | What | DB needed | Speed |
|------|------|-----------|-------|
| Unit | Domain entities, pure logic | No | ~0.2s |
| Integration | Repository against real Postgres | Yes | ~1s |
| E2E | Full HTTP via TestClient | Yes | ~3s |

E2E tests include security checks: role escalation, SQL injection, XSS, JWT tampering, IDOR.

---

## Related docs

- [`specs.md`](./specs.md) — product specification
- [`standards/python.md`](./standards/python.md) — Python coding standards
- [`standards/architecture.md`](./standards/architecture.md) — architecture rules
- [`features/`](./features/) — per-feature implementation docs
