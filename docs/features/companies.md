# Feature: Companies

## Summary

Companies are the top-level tenant entity. Every user, conversation,
resident, and config belongs to exactly one company. A new client =
a new company row in Postgres + a new config document in MongoDB.

Companies have **two data stores** because the data has different needs:

- **Postgres** (`companies` table) — identity: id, slug, name, phone,
  status. Relational — `users.company_id` FK references `companies.id`.
- **MongoDB** (`company_config` collection) — configuration: agent
  settings, WhatsApp tokens, ERP config, feature flags, system prompt.
  Flexible, nested, varies per tenant.

## Why Postgres + MongoDB (not one or the other)?

### Why company identity lives in Postgres

- **FK enforcement** — `users.company_id` references `companies.id`.
  Can't do FKs across Postgres ↔ MongoDB.
- **ACID transactions** — "create company + create first admin user"
  must be atomic. MongoDB doesn't support cross-collection transactions
  with Postgres.
- **Simple schema** — 6 columns, rarely changes, doesn't need flexibility.

### Why company config lives in MongoDB

- **Deeply nested** — the config document has ~50 fields across 8 nested
  objects (whatsapp, agent, priority, langfuse, features, etc.).
  In Postgres this would be 8+ normalized tables or a JSONB blob.
- **Varies per tenant** — one company uses Priority ERP, another uses a
  different ERP. Config shapes are different per company. MongoDB handles
  this naturally; Postgres would need nullable columns or a generic
  key-value table.
- **Changes often** — feature flags toggled, system prompt updated, tools
  enabled/disabled. In Postgres, every structural change = Alembic
  migration. In MongoDB, just set the field.
- **No joins needed** — config is always loaded as a whole document
  (the Config Service fetches it, caches in Redis, passes to the agent).
- **Secret references** — `_ref` pointers to AWS Secrets Manager map
  naturally to nested JSON: `whatsapp.access_token_ref: "acme/whatsapp/access_token"`.

### What would break if we used only one store

| Scenario | Problem |
|----------|---------|
| **Config in Postgres (JSONB)** | Loses type safety, can't index nested fields efficiently, migrations awkward for structural changes. Basically MongoDB inside Postgres — worse at both. |
| **Config in Postgres (normalized)** | 8+ tables. Every new feature flag = Alembic migration. Every new config field = ALTER TABLE. Painful at scale. |
| **Everything in MongoDB** | Lose FK enforcement (users → companies). Lose ACID transactions. Must manually ensure referential integrity. |

## API Endpoints

### Phase 1 (now) — Postgres company CRUD

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/companies` | super_admin | Create a company |
| GET | `/api/v1/companies` | super_admin | List all companies |
| GET | `/api/v1/companies/{id}` | admin+ | Get company by ID |
| PATCH | `/api/v1/companies/{id}` | super_admin | Update company |
| DELETE | `/api/v1/companies/{id}` | super_admin | Soft-delete (status=false) |

### Phase 2 (later) — MongoDB config endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/api/v1/companies/{id}/config` | admin+ | Get resolved config |
| PUT | `/api/v1/companies/{id}/config` | super_admin | Update config + invalidate Redis cache |

## Data Models

### Postgres: `companies` table (exists — migration 0001)

```sql
CREATE TABLE companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    phone       TEXT,
    status      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- `slug` links to the MongoDB `company_config.slug` document
- `status` = soft-delete flag (false = inactive/suspended)
- Already created in migration `0001_create_users_companies_tokens`

### MongoDB: `company_config` collection (Phase 2)

```json
{
  "company_id": "uuid-from-postgres",
  "slug": "acme",
  "name": "Acme Ltd.",
  "status": "active",
  "allowed_buildings": ["בניין א", "בניין ב"],

  "whatsapp": {
    "phone_number": "+972501234567",
    "business_account_id": "123456",
    "webhook_secret_ref": "acme/whatsapp/webhook_secret",
    "access_token_ref": "acme/whatsapp/access_token"
  },

  "agent": {
    "model": "claude-sonnet-4-20250514",
    "system_prompt": "אתה עוזר...",
    "tools": ["search_orders", "get_contacts"],
    "max_tokens": 1000
  },

  "priority": {
    "base_url": "https://...",
    "company": "ACME",
    "username": "api",
    "password_ref": "acme/priority/password"
  },

  "langfuse": {
    "public_key": "pk-lf-...",
    "secret_key_ref": "acme/langfuse/secret_key",
    "project_name": "acme-prod"
  },

  "features": {
    "escalations_page": false,
    "announcements": true,
    "phone_numbers": true
  },

  "meta": {
    "created_at": "2026-04-05T00:00:00Z",
    "updated_at": "2026-04-05T00:00:00Z"
  }
}
```

- Fields ending in `_ref` are **pointers** to AWS Secrets Manager — never
  real secrets. The Config Service resolves them at runtime.
- Convention: `{slug}/{service}/{secret_name}` (e.g. `acme/whatsapp/access_token`)

### The link between Postgres and MongoDB

```
Postgres: companies.slug = "acme"
                ↕
MongoDB:  company_config.slug = "acme"
          company_config.company_id = companies.id
```

`slug` is the human-readable link. `company_id` is the UUID reference.
Both stores have both fields for lookup flexibility.

## Domain (Layer 3)

### Entities

- **`domain/entities/company.py`** — `Company` Pydantic model (already exists)
  - Fields: id, slug, name, phone, is_active, created_at, updated_at
  - Maps `status` (DB column) → `is_active` (domain field)

### Exceptions

- `CompanyNotFoundError` → 404
- `TenantSuspendedError` → 403 (when a suspended company's user tries to act)
- `CompanyAlreadyExistsError` → 409 (duplicate slug)

## Service (Layer 2)

File: `services/company_service.py` — `CompanyService` class

Methods:
- **`create_company(caller, slug, name, phone)`** — super_admin only. Validates slug uniqueness. Creates row in Postgres.
- **`get_company(company_id)`** — find by ID, raise CompanyNotFoundError if missing.
- **`list_companies(caller)`** — super_admin sees all. Admin/manager sees only their own company.
- **`update_company(company_id, **fields)`** — super_admin only. Partial update.
- **`soft_delete_company(company_id)`** — super_admin only. Sets status=false.

### Business rules

- Only super_admin can create, update, and delete companies
- Slug must be unique (used to link Postgres ↔ MongoDB)
- Soft-delete: status=false, no row removal (users still reference the company)
- Admin/manager can GET their own company but not others

## Adapter (Layer 4)

### Repository

File: `adapters/storage/postgres/company/repositories.py` (already exists)

Existing methods: create, find_by_id, find_by_slug

Methods to add:
- `list_all(limit, offset)` — for super_admin
- `update(company_id, **fields)` — partial update
- `find_by_id_check_active(company_id)` — returns company only if status=true

## API (Layer 1)

### Routes

File: `api/v1/companies/router.py`

- `POST ""` → service.create_company(), returns 201
- `GET ""` → service.list_companies(caller), returns list
- `GET "/{company_id}"` → service.get_company(), returns single
- `PATCH "/{company_id}"` → service.update_company(), returns updated
- `DELETE "/{company_id}"` → service.soft_delete_company(), returns 204

### Schemas

File: `api/v1/companies/schemas.py`

**CreateCompanyRequest:**
```json
{
  "slug": "acme",
  "name": "Acme Real Estate Ltd.",
  "phone": "+972501234567"
}
```

**UpdateCompanyRequest:**
```json
{
  "name": "Acme Properties Ltd.",
  "phone": "+972509876543"
}
```

**CompanyResponse:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "acme",
  "name": "Acme Real Estate Ltd.",
  "phone": "+972501234567",
  "is_active": true,
  "created_at": "2026-04-09T12:00:00+03:00",
  "updated_at": "2026-04-09T12:00:00+03:00"
}
```

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_company_entity.py` | (if domain logic added) |
| Integration | `tests/integration/test_company_repo.py` | CRUD + slug uniqueness against real Postgres |
| E2E | `tests/e2e/test_companies.py` | HTTP CRUD, auth/permissions, SQL injection |

## Decisions

- **Postgres for identity, MongoDB for config** — explained above. The
  config document is deeply nested, varies per tenant, and changes often.
  Postgres is for relational data with FK constraints.

- **Slug as the link** — `companies.slug` in Postgres matches
  `company_config.slug` in MongoDB. Human-readable, unique, used in
  URLs and AWS Secrets Manager paths (`{slug}/{service}/{secret_name}`).

- **Soft-delete** — status=false, never remove the row. Users, conversations,
  and configs reference the company. Hard-delete would orphan everything.

- **Config endpoints deferred to Phase 2** — the MongoDB adapter (motor)
  isn't built yet. Phase 1 focuses on Postgres company CRUD. Config
  endpoints come when the WhatsApp webhook flow needs tenant config.

## Swagger

1. Login as super_admin → Authorize
2. **POST `/api/v1/companies`** → create a company with slug + name
3. **GET `/api/v1/companies`** → list all companies
4. **PATCH `/api/v1/companies/{id}`** → update name or phone
5. **DELETE `/api/v1/companies/{id}`** → soft-delete

## Onboarding a new company (full flow)

```
1. super_admin creates company → POST /api/v1/companies
   → Postgres row created (id, slug, name)

2. super_admin stores secrets → AWS Secrets Manager
   → acme/whatsapp/access_token, acme/priority/password, etc.

3. super_admin creates config → POST /api/v1/companies/{id}/config (Phase 2)
   → MongoDB document created with _ref pointers to secrets

4. super_admin creates first admin → POST /api/v1/users
   → Postgres user row with company_id = new company's id

5. Admin receives invite email → logs in → manages their company
```
