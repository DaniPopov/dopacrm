# Feature: Tenants

## Summary

Tenant (gym) management — onboarding, configuration, and lifecycle for
gyms on the platform. Only super_admin can create, update, list, or
suspend tenants. Each tenant is a gym with its own slug, timezone,
currency, locale, and status.

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | `/api/v1/tenants` | super_admin | 60/min/user | Onboard a new gym |
| GET | `/api/v1/tenants` | super_admin | 60/min/user | List all tenants |
| GET | `/api/v1/tenants/{id}` | Bearer | 60/min/user | Get tenant by ID |
| PATCH | `/api/v1/tenants/{id}` | super_admin | 60/min/user | Partial update |
| POST | `/api/v1/tenants/{id}/suspend` | super_admin | 60/min/user | Suspend tenant |

## Domain (Layer 3)

### Entities

- **`domain/entities/tenant.py`** — `Tenant` Pydantic model + `TenantStatus` StrEnum
  - Fields: id, slug, name, phone, status, timezone, currency, locale, trial_ends_at, created_at, updated_at
  - `TenantStatus`: trial / active / suspended / cancelled

### Pure logic methods

- `Tenant.is_active()` — True if status is `trial` or `active`

### Exceptions

- `TenantNotFoundError` → 404
- `TenantSuspendedError` → 403
- `TENANT_SLUG_TAKEN` → 409

## Service (Layer 2)

File: `services/tenant_service.py`

- `create_tenant(caller, slug, name, ...)` — permission check + repo create + commit
- `get_tenant(tenant_id)` — fetch by ID or raise
- `get_tenant_by_slug(slug)` — fetch by slug or raise
- `list_tenants(caller, limit, offset)` — super_admin only, paginated
- `update_tenant(caller, tenant_id, **fields)` — super_admin only, partial update
- `suspend_tenant(caller, tenant_id)` — super_admin only, sets status to suspended

### Business rules (what the service enforces)

- Only super_admin can create, update, list, or suspend tenants
- Slug must be unique (409 if taken)
- Suspend sets status to `suspended` — tenants in this state should be blocked from API access (enforcement to be added as middleware)

## Adapter (Layer 4)

### Database model

File: `adapters/storage/postgres/tenant/models.py`

Table: `tenants`

| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK, gen_random_uuid() |
| slug | text | UNIQUE, NOT NULL |
| name | text | NOT NULL |
| phone | text | nullable |
| status | text | NOT NULL, CHECK (trial/active/suspended/cancelled), default 'active' |
| timezone | text | NOT NULL, default 'Asia/Jerusalem' |
| currency | text | NOT NULL, default 'ILS' |
| locale | text | NOT NULL, default 'he-IL' |
| trial_ends_at | timestamptz | nullable |
| created_at | timestamptz | NOT NULL, default now() |
| updated_at | timestamptz | NOT NULL, default now(), auto-update |

### Repository methods

File: `adapters/storage/postgres/tenant/repositories.py`

- `create(slug, name, ...)` — INSERT, catches IntegrityError → TenantAlreadyExistsError
- `find_by_id(tenant_id)` — SELECT by PK
- `find_by_slug(slug)` — SELECT by unique slug
- `list_all(limit, offset)` — paginated, ordered by created_at DESC
- `update(tenant_id, **fields)` — partial UPDATE

### Migrations

- `0001_create_users_companies_tokens.py` — creates initial `tenants` table (boolean status)
- `0002_expand_tenants.py` — status boolean → text, adds timezone, currency, locale, trial_ends_at

## API (Layer 1)

### Routes

File: `api/v1/tenants/router.py`

- `POST /` — parse CreateTenantRequest, call service.create_tenant, return 201
- `GET /` — super_admin only, call service.list_tenants, return list
- `GET /{tenant_id}` — any authenticated user, call service.get_tenant
- `PATCH /{tenant_id}` — super_admin only, call service.update_tenant
- `POST /{tenant_id}/suspend` — super_admin only, call service.suspend_tenant

### Schemas

File: `api/v1/tenants/schemas.py`

**CreateTenantRequest:**
```json
{
  "slug": "ironfit-tlv",
  "name": "IronFit Tel Aviv",
  "phone": "+972-3-555-1234",
  "timezone": "Asia/Jerusalem",
  "currency": "ILS",
  "locale": "he-IL"
}
```

**TenantResponse:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "ironfit-tlv",
  "name": "IronFit Tel Aviv",
  "phone": "+972-3-555-1234",
  "status": "active",
  "timezone": "Asia/Jerusalem",
  "currency": "ILS",
  "locale": "he-IL",
  "trial_ends_at": null,
  "created_at": "2026-04-10T12:00:00+03:00",
  "updated_at": "2026-04-10T12:00:00+03:00"
}
```

### Dependencies used

- `require_super_admin` — permission gate for create/update/list/suspend
- `get_current_user` — JWT validation for get-by-id
- `api_rate_limit` — 60/min per user

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_tenant_entity.py` | Entity pure logic (is_active) |
| Integration | `tests/integration/test_tenant_repo.py` | Repo against real Postgres |
| E2E | `tests/e2e/test_tenants.py` | Full HTTP route tests + security |

## Decisions

- **Status as text enum, not boolean** — supports trial/active/suspended/cancelled lifecycle
- **Israel defaults** — timezone Asia/Jerusalem, currency ILS, locale he-IL (operator is in Israel)
- **super_admin only for all mutations** — gym owners don't self-register in v1, they're onboarded by the platform
- **No hard delete** — suspend instead, preserving all data

## Swagger

How to test from http://localhost:8000/docs:

1. Login as super_admin → copy token → Authorize
2. POST /api/v1/tenants with slug + name
3. GET /api/v1/tenants — verify it appears
4. PATCH /api/v1/tenants/{id} — update the name
5. POST /api/v1/tenants/{id}/suspend — verify status changes to "suspended"
