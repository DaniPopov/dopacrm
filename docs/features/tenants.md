# Feature: Tenants

## Summary

Tenant (gym) management — onboarding, configuration, and lifecycle for
gyms on the platform. Only super_admin can create, update, list, or
suspend tenants.

Every new tenant is automatically:
- Placed on the default SaaS plan (500 ILS/month, 1000 members)
- Set to ``trial`` status with a 14-day trial window
- Given Israel regional defaults (``Asia/Jerusalem``, ``ILS``, ``he-IL``, address country ``IL``)

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
  - Identity: `id`, `slug`, `name`
  - Status: `status` (trial/active/suspended/cancelled), `trial_ends_at`
  - Plan: `saas_plan_id` (FK → saas_plans)
  - Branding: `logo_url`
  - Contact: `phone`, `email`, `website`
  - Address: `address_street`, `address_city`, `address_country` (default `IL`), `address_postal_code`
  - Legal: `legal_name`, `tax_id` (ח.פ / ע.מ)
  - Regional: `timezone` (`Asia/Jerusalem`), `currency` (`ILS`), `locale` (`he-IL`)
  - Timestamps: `created_at`, `updated_at`

### Pure logic methods

- `Tenant.is_active()` — True if status is `trial` or `active`

### Exceptions

- `TenantNotFoundError` → 404
- `TenantSuspendedError` → 403
- `TENANT_SLUG_TAKEN` → 409
- `MISSING_DEFAULT_PLAN` → 500 (seed data missing — should never happen in prod)

## Service (Layer 2)

File: `services/tenant_service.py`

- `create_tenant(caller, slug, name, ...)` — permission check, auto-fetch default plan, set status=trial, set trial_ends_at=now+14d, repo create, commit
- `get_tenant(tenant_id)` — fetch by ID or raise
- `get_tenant_by_slug(slug)` — fetch by slug or raise
- `list_tenants(caller, limit, offset)` — super_admin only, paginated
- `update_tenant(caller, tenant_id, **fields)` — super_admin only, partial update
- `suspend_tenant(caller, tenant_id)` — super_admin only, sets status to suspended

Constants:
- `TRIAL_PERIOD = timedelta(days=14)`

### Business rules (what the service enforces)

- Only super_admin can create, update, list, or suspend tenants
- Slug must be unique (409 if taken)
- New tenants always start on the default SaaS plan (`code='default'`)
- New tenants always start in `trial` status with 14-day `trial_ends_at`
- Suspend sets status to `suspended` — tenants in this state should be blocked from API access (enforcement to be added as middleware)

## Adapter (Layer 4)

### Database model

File: `adapters/storage/postgres/tenant/models.py`

Table: `tenants`

| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK, `gen_random_uuid()` |
| slug | text | UNIQUE, NOT NULL |
| name | text | NOT NULL |
| status | text | NOT NULL, CHECK (trial/active/suspended/cancelled), default `'active'` |
| saas_plan_id | uuid | NOT NULL, FK → `saas_plans.id`, ON DELETE RESTRICT |
| logo_url | text | nullable |
| phone | text | nullable |
| email | text | nullable |
| website | text | nullable |
| address_street | text | nullable |
| address_city | text | nullable |
| address_country | text | nullable, default `'IL'` |
| address_postal_code | text | nullable |
| legal_name | text | nullable |
| tax_id | text | nullable |
| timezone | text | NOT NULL, default `'Asia/Jerusalem'` |
| currency | text | NOT NULL, default `'ILS'` |
| locale | text | NOT NULL, default `'he-IL'` |
| trial_ends_at | timestamptz | nullable |
| created_at | timestamptz | NOT NULL, default `now()` |
| updated_at | timestamptz | NOT NULL, default `now()`, auto-update |

### Repository methods

File: `adapters/storage/postgres/tenant/repositories.py`

- `create(slug, name, saas_plan_id, ...)` — INSERT, catches IntegrityError → TenantAlreadyExistsError
- `find_by_id(tenant_id)` — SELECT by PK
- `find_by_slug(slug)` — SELECT by unique slug
- `list_all(limit, offset)` — paginated, ordered by created_at DESC
- `update(tenant_id, **fields)` — partial UPDATE

### Migrations

- `0001_create_users_companies_tokens.py` — initial `tenants` table (boolean status)
- `0002_expand_tenants.py` — status boolean → text, adds timezone, currency, locale, trial_ends_at
- `0003_create_saas_plans.py` — seeds the default SaaS plan referenced below
- `0004_expand_tenants_and_users.py` — adds saas_plan_id (FK), logo_url, email, website, address_*, legal_name, tax_id (plus first_name/last_name/phone on users)

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

**CreateTenantRequest** — only `slug` and `name` are required, everything else optional:
```json
{
  "slug": "ironfit-tlv",
  "name": "IronFit Tel Aviv",
  "phone": "+972-3-555-1234",
  "email": "info@ironfit.co.il",
  "website": "https://ironfit.co.il",
  "address_street": "Rothschild 1",
  "address_city": "Tel Aviv",
  "address_country": "IL",
  "address_postal_code": "6578901",
  "legal_name": "IronFit Ltd",
  "tax_id": "123456789",
  "timezone": "Asia/Jerusalem",
  "currency": "ILS",
  "locale": "he-IL"
}
```

**TenantResponse** — includes all fields plus server-assigned data (status, saas_plan_id, trial_ends_at):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "ironfit-tlv",
  "name": "IronFit Tel Aviv",
  "status": "trial",
  "saas_plan_id": "aaaa0000-0000-0000-0000-000000000000",
  "logo_url": null,
  "phone": "+972-3-555-1234",
  "email": "info@ironfit.co.il",
  "website": "https://ironfit.co.il",
  "address_street": "Rothschild 1",
  "address_city": "Tel Aviv",
  "address_country": "IL",
  "address_postal_code": "6578901",
  "legal_name": "IronFit Ltd",
  "tax_id": "123456789",
  "timezone": "Asia/Jerusalem",
  "currency": "ILS",
  "locale": "he-IL",
  "trial_ends_at": "2026-04-25T12:00:00+03:00",
  "created_at": "2026-04-11T12:00:00+03:00",
  "updated_at": "2026-04-11T12:00:00+03:00"
}
```

### Dependencies used

- `require_super_admin` — permission gate for create/update/list/suspend
- `get_current_user` — JWT validation for get-by-id
- `api_rate_limit` — 60/min per user

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_tenant_entity.py` | Entity pure logic, required fields, defaults |
| Integration | `tests/integration/test_tenant_repo.py` | Repo against real Postgres (create with full fields, FK to saas_plans) |
| E2E | `tests/e2e/test_tenants.py` | Full HTTP route tests + security |

## Decisions

- **Status as text enum, not boolean** — supports trial/active/suspended/cancelled lifecycle
- **Israel defaults** — timezone Asia/Jerusalem, currency ILS, locale he-IL, address_country IL (operator is in Israel)
- **super_admin only for all mutations** — gym owners don't self-register in v1, they're onboarded by the platform
- **No hard delete** — suspend instead, preserving all data
- **Auto 14-day trial** — every new tenant starts in `trial` status with `trial_ends_at = now + 14 days`. Simpler than self-serve signup. Trial enforcement (blocking access after expiry) will be added as middleware.
- **Auto default plan assignment** — the service fetches the `default` SaaS plan and assigns it automatically. Super_admin doesn't pick a plan at creation time because there's only one plan in v1.
- **FK ON DELETE RESTRICT** — you can't delete a SaaS plan that has tenants on it. Protects against accidental plan deletion breaking multiple tenants.
- **Logo URL, not upload** — the tenant row stores an S3 key (uploaded separately via `POST /api/v1/uploads/logo`, which isn't built yet). Keeps tenant creation atomic and lets us validate/retry uploads independently.
- **Tax ID as text, not validated** — Israeli business numbers (ח.פ / ע.מ) are 9 digits but we don't enforce format at the schema level yet. Can add Pydantic validation later.

## Swagger

1. Login as super_admin → copy token → Authorize
2. POST /api/v1/tenants with slug + name
3. GET /api/v1/tenants — verify it appears with `status=trial`
4. PATCH /api/v1/tenants/{id} — update the name
5. POST /api/v1/tenants/{id}/suspend — verify status changes to `suspended`
