# Feature: SaaS Plans

## Summary

DopaCRM's own pricing tiers — what a gym (tenant) pays to use the
platform. **Not** the same as membership plans, which are what the gym
sells to its own members.

In v1 (POC) we ship with one plan: **DopaCRM Standard** — 500 ILS/month,
up to 1000 members, unlimited staff users. The full schema is
intentionally broader so we can add Free/Starter/Pro tiers later
without another migration.

No API endpoints in v1 — plans are seeded via migration, not managed
through the dashboard. The only code that reads SaaS plans is the
tenant creation flow (which FKs into the plan at signup).

## API Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| *(none in v1)* | — | — | Seeded via migration |

Planned for v2:
- `GET /api/v1/saas-plans` — list public plans (for self-serve signup)
- `POST /api/v1/saas-plans` — super_admin creates custom plans
- `PATCH /api/v1/saas-plans/{id}` — update limits/price

## Domain (Layer 3)

### Entities

- **`domain/entities/saas_plan.py`** — `SaasPlan` Pydantic model + `BillingPeriod` StrEnum
  - Fields: id, code, name, price_cents, currency, billing_period, max_members, max_staff_users, features, is_public, created_at, updated_at
  - `BillingPeriod`: `monthly` / `yearly`

### Exceptions

- *(none specific to SaaS plans yet — tenant limits raise `TenantLimitExceededError`, TBD)*

## Service (Layer 2)

*(no service layer yet — no business logic, just reads. Tenant service fetches the default plan directly via the repo.)*

## Adapter (Layer 4)

### Database model

File: `adapters/storage/postgres/saas_plan/models.py`

Table: `saas_plans`

| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK, gen_random_uuid() |
| code | text | UNIQUE, NOT NULL — stable identifier (e.g. `"default"`) |
| name | text | NOT NULL — display name (e.g. `"DopaCRM Standard"`) |
| price_cents | int | NOT NULL, CHECK >= 0 — smallest currency unit |
| currency | text | NOT NULL, default `'ILS'` — ISO 4217 |
| billing_period | text | NOT NULL, default `'monthly'`, CHECK IN (monthly, yearly) |
| max_members | int | NOT NULL, CHECK >= 0 — hard cap on gym members |
| max_staff_users | int | nullable — NULL means unlimited |
| features | jsonb | NOT NULL, default `'{}'::jsonb` |
| is_public | boolean | NOT NULL, default `true` — visible on signup? |
| created_at | timestamptz | NOT NULL, default `now()` |
| updated_at | timestamptz | NOT NULL, default `now()`, auto-updated on modify |

Why each column:
- **`code`** vs **`id`** — `id` is a random UUID that differs across environments; `code` is a stable string that references the same logical plan everywhere (`"default"` in dev matches `"default"` in prod). Code does lookups by code, never by ID.
- **`price_cents`** as int — money is always stored as the smallest unit to avoid float rounding errors.
- **`max_staff_users`** nullable — `NULL` = unlimited. Simpler than a magic number like `-1` or `999999`.
- **`features` as jsonb** — each plan can unlock different feature flags without schema changes.
- **`CheckConstraint`s** — database-level invariants. Even if Python has a bug, Postgres rejects bad data.

### Repository methods

File: `adapters/storage/postgres/saas_plan/repositories.py`

- `find_by_id(plan_id)` — fetch by UUID, returns None if not found
- `find_by_code(code)` — fetch by stable code (e.g. `"default"`)
- `find_default()` — shortcut for `find_by_code("default")`, used by tenant creation
- `list_public()` — all plans where `is_public=True`, ordered by price ascending

### Migrations

- `0003_create_saas_plans.py` — creates the table + seeds the default plan

The seed is part of the migration itself:

```sql
INSERT INTO saas_plans (code, name, price_cents, currency, billing_period,
                        max_members, max_staff_users, features, is_public)
VALUES ('default', 'DopaCRM Standard', 50000, 'ILS', 'monthly',
        1000, NULL, '{}'::jsonb, true)
```

This means running `make migrate-up-dev` on a fresh DB gives you a
working plan immediately. No separate seed script needed.

## API (Layer 1)

*(no API layer yet — intentional. Plans are internal infrastructure; the
frontend doesn't need to list or create them in v1.)*

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_saas_plan_entity.py` | Default values (ILS, monthly, public), staff cap nullability, price/member validation |
| Integration | `tests/integration/test_saas_plan_repo.py` | find_by_id, find_by_code, find_default, list_public, not-found cases |

### Test count

- Unit: 4 tests
- Integration: 6 tests
- **Total: 10 tests, all passing**

## Decisions

- **No API endpoints in v1** — plans are seeded via migration. Super_admin
  doesn't manage plans through the dashboard because there's only one
  plan. When we add Free/Starter/Pro, we add the API.

- **`code` vs `id`** — keeping a stable string identifier (`code`) separate
  from the UUID primary key. Lets us hardcode `find_default("default")`
  without worrying about which env we're in.

- **Single seeded plan for POC** — one plan (500 ILS / 1000 members /
  unlimited staff) to keep onboarding simple. Pricing will be revisited
  with the team before launch.

- **Money as int cents** — never floats. `500 ILS = 50000`. Avoids all
  rounding issues.

- **`max_staff_users` nullable** — NULL means unlimited. Cleaner than
  sentinel values like `-1` or `999999`.

- **Features as JSONB, not separate columns** — feature flags evolve
  over time. JSONB lets us add `{"custom_branding": true}` without a
  migration every time.

- **CheckConstraints in the schema** — database-level invariants
  (`price_cents >= 0`, `max_members >= 0`, `billing_period IN ('monthly', 'yearly')`).
  Belt-and-suspenders with Pydantic validation — if Python has a bug,
  Postgres still rejects bad data.

- **Seed in the migration itself** — the first `INSERT` lives inside the
  `upgrade()` function. Running `make migrate-up-dev` on a fresh DB gives
  you a working plan immediately. No separate seed script means less
  environment drift.

## Current seed

One row, inserted by migration `0003`:

```json
{
  "code": "default",
  "name": "DopaCRM Standard",
  "price_cents": 50000,
  "currency": "ILS",
  "billing_period": "monthly",
  "max_members": 1000,
  "max_staff_users": null,
  "features": {},
  "is_public": true
}
```

## Planned

- **Multi-tier plans** — Free / Starter / Growth / Pro / Enterprise with
  different limits and prices. Will be added once pricing is finalized
  with the team.
- **Plan change history** — a `tenant_plan_changes` table tracking
  when a tenant upgraded/downgraded, for revenue reporting.
- **Stripe integration** — actual billing (recurring charges, invoices,
  trials, cancellations). V2+.
- **Feature flag enforcement** — middleware that checks `tenant.config.features`
  before letting a feature run (e.g., "custom_branding" gated).
- **Member limit enforcement** — service-layer check on member creation
  that compares current count to `tenant.saas_plan.max_members`. Will be
  added when the Members feature is built.
