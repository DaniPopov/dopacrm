# DopaCRM — Product Specification

> Living document. Last updated: 2026-04-11.
>
> This is the source of truth for what DopaCRM does, who it serves, and how the domain is modeled. Architecture and coding conventions live in `CLAUDE.md` and `docs/standards/`. Per-feature implementation details live in `docs/features/`.

---

## 1. Vision

**DopaCRM is a SaaS CRM built specifically for gyms and fitness studios — and the most flexible one on the market.**

Most general-purpose CRMs treat a gym like any other small business — a contact list with a pipeline bolted on. They miss the rhythms that actually run a gym: recurring memberships, class attendance, drop-ins, trial passes, freezes, churn at month-end, and the constant churn-and-replace of leads coming through the door.

But even gym-specific CRMs have a second problem: **they're rigid**. You get the features the vendor built, the roles the vendor defined, the fields the vendor chose. A gym with three trainers, a front-desk cashier, and a separate sales team has to twist their workflow to match the software.

DopaCRM flips that. It gives gym owners **one place to run their business** — members, revenue, leads, plans — and lets them **shape the software to fit how their gym actually operates**, not the other way around.

### Guiding principles

1. **Built for gyms, not adapted to them.** Every concept (member, lead, plan, freeze, drop-in) maps directly to how a gym operates.
2. **Owner-configurable by default.** Roles, fields, plans, workflows, dashboards — the owner defines their world. Only `super_admin` and `owner` are system-defined; everything else is customizable per-tenant. This is the product's core differentiator, not a v2 feature.
3. **Owner-first.** The primary user is the person who runs the gym. Features answer Monday-morning questions: *"How much did we make? Who's about to churn? Which leads haven't been called?"*
4. **Boring where it matters.** Billing, member records, and revenue numbers must be correct and auditable.
5. **Fast to onboard.** A new gym should see real data the same day they sign up — with sensible defaults that the owner can customize later.

### What "flexible" means concretely

| Area | Rigid CRMs | DopaCRM |
|---|---|---|
| **Roles** | Fixed: Admin / Staff / Sales | `super_admin` + `owner` are system. Every other role is owner-created with custom feature grants. See [`docs/features/roles.md`](./features/roles.md). |
| **Member fields** | Hardcoded schema | JSONB `custom_fields` — owner adds "belt color", "injury notes", "referral source" without a migration |
| **Plan attributes** | Fixed columns | JSONB `custom_attrs` — owner defines per-plan extras (PT sessions included, valid days, guest passes) |
| **Feature visibility** | All users see all features their role allows | Owner picks which features each non-owner role can see |
| **Dashboards** | Same for everyone | Widget layout per user (v2) |
| **Pricing tiers, billing cadences** | Vendor-defined | Owner-defined per tenant |

---

## 2. Target Users

| User | What they need |
|------|----------------|
| **Gym owner / operator** | Revenue at a glance, member growth, churn signals, lead pipeline health |
| **Front-desk staff** | Check members in, sell drop-ins, log a new lead, record a payment |
| **Sales / membership consultant** | Work the lead pipeline, schedule trials, follow up, convert |
| **Trainer** *(later)* | See their clients, schedule sessions, log attendance |

MVP focuses on **owners and front-desk staff**.

---

## 3. Modules

### 3.1 Tenant Management (Gyms)

A tenant is a gym. Everything else belongs to a tenant.

**Stored in:** PostgreSQL (`tenants` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK. Cross-DB reference key |
| slug | text | URL-safe (`ironfit-tlv`). Unique. Mutable |
| name | text | Display name |
| status | text | `trial`, `active`, `suspended`, `cancelled`. Default: `active`. CHECK constraint |
| saas_plan_id | uuid | FK → `saas_plans`. NOT NULL. ON DELETE RESTRICT |
| logo_url | text | Nullable. S3 key from `/uploads/logo` |
| phone | text | Nullable. Business phone |
| email | text | Nullable. Business email |
| website | text | Nullable |
| address_street | text | Nullable |
| address_city | text | Nullable |
| address_country | text | Nullable. Default: `IL` (ISO 3166-1 alpha-2) |
| address_postal_code | text | Nullable |
| legal_name | text | Nullable. Legal business name (may differ from display) |
| tax_id | text | Nullable. ח.פ / ע.מ for Israeli businesses |
| timezone | text | NOT NULL. IANA. Default: `Asia/Jerusalem` |
| currency | text | NOT NULL. ISO 4217. Default: `ILS` |
| locale | text | NOT NULL. BCP 47. Default: `he-IL` |
| trial_ends_at | timestamptz | Nullable. Set to `now + 14 days` at signup |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Auto-set at signup (not provided by client):**
- `status = 'trial'` — every new tenant starts on a trial
- `trial_ends_at = now + 14 days`
- `saas_plan_id = default plan id` — auto-assigned via `SaasPlanRepository.find_default()`

**Tenant config** is stored in **MongoDB** (`tenant_configs` collection, keyed by `tenant_id`). Contains feature flags, operational limits, and plan-specific settings:

```json
{
  "tenant_id": "550e8400-...",
  "limits": {
    "max_members": 250,
    "max_staff_users": 5,
    "max_membership_plans": 10
  },
  "features": {
    "lead_pipeline": true,
    "custom_plan_attributes": true,
    "export_to_csv": false,
    "stripe_integration": false
  }
}
```

Config is seeded from the SaaS plan at signup, can be overridden per-tenant (custom enterprise deals).

---

### 3.2 SaaS Plans (DopaCRM pricing tiers)

What the **gym pays DopaCRM** for. Not the same as membership plans (what members pay the gym).

**Stored in:** PostgreSQL (`saas_plans` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| code | text | Stable identifier: `free`, `starter`, `pro`. Unique |
| name | text | Display name |
| price_cents | int | Monthly price in smallest currency unit |
| currency | text | ISO 4217 |
| billing_period | text | `monthly`, `yearly` |
| max_members | int | Hard cap |
| max_staff_users | int | Hard cap |
| features | jsonb | Feature flags this plan grants |
| is_public | boolean | Visible for self-serve signup |

---

### 3.3 User Management (Staff)

Staff members who log in. A user belongs to exactly one tenant (except `super_admin` who is platform-level).

**Stored in:** PostgreSQL (`users` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants`. Nullable for super_admin |
| email | text | Login identifier |
| hashed_password | text | Argon2 |
| first_name | text | |
| last_name | text | |
| role | text | *Current:* enum literal. *Planned:* FK to `tenant_roles.id`. See below. |
| status | text | `invited`, `active`, `disabled` |
| last_login_at | timestamptz | |

**Roles & permissions — current state (transitional):**

Today `users.role` is a text column holding one of four literals: `super_admin`, `owner`, `staff`, `sales`. This is a temporary shape — the real model is dynamic, per-tenant, owner-configurable (see below).

| Role | Scope | Can do |
|------|-------|--------|
| `super_admin` | Platform | Onboard gyms, create first user per tenant, manage SaaS plans |
| `owner` | Tenant | Everything within their gym: config, billing, users, members, leads |
| `staff` | Tenant | Default "operations" role — seeded for new tenants, editable by owner |
| `sales` | Tenant | Default "lead pipeline" role — seeded for new tenants, editable by owner |

**Planned: dynamic roles (see [`docs/features/roles.md`](./features/roles.md)):**

In line with the flexibility principle, only `super_admin` and `owner` are system-defined. Every other role is a row in `tenant_roles` that the owner creates, names, and assigns feature grants to. New tenants are seeded with "Staff" and "Sales" as starting points; owners can rename, delete, or add new roles like "Receptionist", "Trainer", "Night Shift Manager", "Cashier".

When this lands, `users.role` becomes `users.role_id UUID REFERENCES tenant_roles(id)`, and `/auth/me` returns the role as an object (`{name, features, is_system}`) so the frontend can permission-check without a hardcoded role list.

**Business rules:**
- Only `super_admin` creates tenants and first-users
- `owner` can create other users within their tenant
- Non-super_admin roles always require `tenant_id`
- Each tenant should have at least one `owner`
- `super_admin` and `owner` roles cannot be renamed or deleted (system roles)

---

### 3.4 Member Management

The core of the CRM — the gym's customers.

**Stored in:** PostgreSQL (`members` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants` |
| first_name | text | |
| last_name | text | |
| email | text | Nullable — not all gym members have email |
| phone | text | Primary contact method |
| date_of_birth | date | Nullable |
| gender | text | Nullable |
| status | text | `active`, `frozen`, `cancelled`, `expired` |
| join_date | date | When they first joined |
| notes | text | Free-text |
| custom_fields | jsonb | Per-tenant flexibility |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Key operations:**
- Create / update / view member profile
- Change status (active → frozen → active, active → cancelled)
- View member's subscription history, payment history, activity
- Search / filter members by name, status, plan, join date
- Bulk import (CSV) for onboarding existing gyms

**Business rules:**
- A member without an active subscription is `expired`, not `active`
- Freezing a member pauses their subscription but doesn't cancel it
- Cancellation is a terminal state for a subscription (member can rejoin on a new one)
- Member count is checked against `tenant_config.limits.max_members` on create

---

### 3.5 Membership Plans (what the gym sells)

Products the gym offers to its members. Each gym defines their own.

**Stored in:** PostgreSQL (`membership_plans` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants` |
| name | text | "Monthly Unlimited", "10-Class Pack" |
| description | text | Nullable |
| type | text | `recurring`, `one_time` |
| price_cents | int | In tenant's currency |
| currency | text | Inherited from tenant |
| billing_period | text | `monthly`, `quarterly`, `yearly`, `one_time` |
| duration_days | int | For one-time plans (e.g., 30-day trial pass) |
| is_active | boolean | Can new members subscribe to this? |
| custom_attrs | jsonb | Gym-specific flexibility |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**`custom_attrs` examples** (varies per gym):
```json
{ "includes_pt_sessions": 2, "valid_days": ["mon","wed","fri"], "guest_passes": 1 }
```

**Business rules:**
- Plan count checked against `tenant_config.limits.max_membership_plans`
- Deactivating a plan doesn't affect existing subscriptions — only prevents new ones
- Price changes don't retroactively affect existing subscriptions

---

### 3.6 Subscriptions

The link between a member and a membership plan.

**Stored in:** PostgreSQL (`subscriptions` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants` |
| member_id | uuid | FK → `members` |
| plan_id | uuid | FK → `membership_plans` |
| status | text | `active`, `frozen`, `cancelled`, `expired` |
| price_cents | int | Locked at subscription time (plan price can change later) |
| started_at | date | |
| expires_at | date | Nullable (recurring plans auto-renew) |
| frozen_at | date | Nullable |
| frozen_until | date | Nullable |
| cancelled_at | date | Nullable |
| cancellation_reason | text | Nullable |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Business rules:**
- A member can have only one `active` subscription at a time
- Freezing sets `frozen_at` + optional `frozen_until`, pauses billing
- When `frozen_until` passes, subscription auto-unfreezes
- Cancellation is final — member needs a new subscription to rejoin
- `price_cents` is locked at subscription time — protects against retroactive price changes
- Expiry is checked daily (or on access) for one-time plans

---

### 3.7 Payments & Revenue

Recorded income events. DopaCRM **records** payments — it doesn't process cards (v1).

**Stored in:** PostgreSQL (`payments` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants` |
| member_id | uuid | FK → `members` |
| subscription_id | uuid | FK → `subscriptions`. Nullable (drop-in payment may not have one) |
| amount_cents | int | |
| currency | text | |
| payment_method | text | `cash`, `card`, `bank_transfer`, `other` |
| description | text | Nullable |
| paid_at | timestamptz | When the payment was actually made |
| recorded_by | uuid | FK → `users`. Who entered it |
| created_at | timestamptz | |

**Key queries the dashboard needs:**
- Total revenue this month / last month / MoM change
- Revenue per plan
- Revenue per member (lifetime value)
- Average revenue per member
- Payment method breakdown

**Business rules:**
- Payments are append-only — no editing, no deleting. If a mistake is made, record a corrective entry (negative amount or credit note).
- `paid_at` may differ from `created_at` (backdated entries are allowed)

---

### 3.8 Lead Management

Prospective members moving through a pipeline.

**Stored in:** PostgreSQL (`leads` table)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid | PK |
| tenant_id | uuid | FK → `tenants` |
| first_name | text | |
| last_name | text | |
| email | text | Nullable |
| phone | text | |
| source | text | `walk_in`, `website`, `referral`, `social_media`, `ad`, `other` |
| status | text | `new`, `contacted`, `trial`, `converted`, `lost` |
| assigned_to | uuid | FK → `users`. Nullable |
| notes | text | Nullable |
| converted_member_id | uuid | FK → `members`. Set when status = `converted` |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Lead activity feed:** stored in **MongoDB** (`lead_activities` collection):
```json
{
  "lead_id": "...",
  "tenant_id": "...",
  "type": "call",
  "note": "Called, interested in monthly plan. Booked trial for Friday.",
  "created_by": "user-uuid",
  "created_at": "2026-04-10T10:30:00Z"
}
```

Activity types: `call`, `email`, `note`, `status_change`, `trial_booked`, `trial_completed`.

**Pipeline stages:**
```
new → contacted → trial → converted
                       ↘ lost
```

**Business rules:**
- Converting a lead creates a `Member` and links via `converted_member_id`
- Lost leads can be reopened (status back to `contacted`)
- Lead source tracking for "where do our members come from?" reporting

---

### 3.9 Dashboard

**One route (`/dashboard`), role-based content.** The page checks the user's role and renders the appropriate view. No separate routes for admin vs gym dashboards.

#### Super Admin Dashboard

Platform-level overview. Only visible to `super_admin`.

| Widget | What it shows |
|--------|--------------|
| Total tenants | Count by status (active / trial / suspended / cancelled) |
| Total users | Count across the entire platform |
| New tenants this month | Onboarding velocity |
| Platform revenue | Sum across all tenants (when billing is implemented) |

#### Gym Dashboard (owner / staff / sales)

Tenant-scoped. Each gym sees only their own data.

| Widget | What it shows |
|--------|--------------|
| Active members | Count with `status = active` |
| MRR | Sum of active recurring subscription prices |
| New members this month | Members with `join_date` in current month |
| Churn this month | Members who cancelled + churn rate |
| Revenue this month | Sum of payments with `paid_at` in current month |
| Revenue last month | Previous month + MoM change % |
| Leads in pipeline | Count by status (new, contacted, trial) |
| Lead conversion rate | Converted / total leads this month |

#### Customizable dashboards (future)

Gym owners will be able to choose which widgets to show, set date ranges, and arrange layout. Config stored in MongoDB (`user_dashboard_configs`):

```json
{
  "user_id": "...",
  "tenant_id": "...",
  "layout": [
    { "widget": "revenue_this_month", "position": { "x": 0, "y": 0, "w": 6, "h": 4 } },
    { "widget": "active_members", "position": { "x": 6, "y": 0, "w": 3, "h": 4 } },
    { "widget": "churn_rate", "position": { "x": 9, "y": 0, "w": 3, "h": 4 } },
    { "widget": "leads_pipeline", "position": { "x": 0, "y": 4, "w": 12, "h": 4 } }
  ],
  "default_date_range": "this_month"
}
```

Not implemented in v1 — gym owners get the default layout above. Customization comes in v2.

---

## 4. Data Architecture

### PostgreSQL (primary — transactional entities)

All core business entities: `tenants`, `saas_plans`, `users`, `members`, `membership_plans`, `subscriptions`, `payments`, `leads`, `refresh_tokens`.

JSONB columns for per-entity flexibility: `membership_plans.custom_attrs`, `members.custom_fields`.

### MongoDB (config + document-shaped data)

- `tenant_configs` — per-gym feature flags, limits, settings
- `activity_logs` — append-only system events per tenant
- `lead_activities` — activity feed per lead (calls, notes, status changes)
- `audit_trails` — who changed what, when
- `integration_payloads` — raw webhook payloads from external services (Stripe, etc.)

### Redis

- Config cache (hot-path reads of tenant config)
- Session / rate limit counters
- Temporary state (e.g., email verification tokens)

### Cross-database identity

Mongo documents reference Postgres entities by **UUID** (`tenant_id`, `lead_id`, `member_id`). Never by slug or name.

---

## 5. Multi-tenancy

- **Shared schema** with `tenant_id` on every table (not schema-per-tenant)
- Every query is scoped by `tenant_id`, extracted from JWT
- Tenant isolation is enforced at the **service layer** — services always receive `tenant_id` and pass it to repositories
- Redis caching is namespaced by `tenant_id`
- MongoDB collections include `tenant_id` on every document

---

## 6. API Design (overview)

Versioned under `/api/v1/`. RESTful. JSON request/response bodies.

### Auth
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/auth/login` | None | Email + password → JWT (HttpOnly cookie + response body) |
| POST | `/api/v1/auth/logout` | Cookie/Bearer | Clears cookie + blacklists token in Redis |
| GET | `/api/v1/auth/me` | Cookie/Bearer | Current user profile |

**Auth security:** JWT stored in HttpOnly cookie (XSS-immune). Redis blacklist on logout (token can't be reused). Dual support: cookie (frontend) + Bearer header (Swagger/API clients).

### Tenants
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/tenants` | super_admin | Onboard a new gym |
| GET | `/api/v1/tenants` | super_admin | List all tenants |
| GET | `/api/v1/tenants/{id}` | Bearer | Get tenant by ID |
| PATCH | `/api/v1/tenants/{id}` | super_admin | Update tenant |
| POST | `/api/v1/tenants/{id}/suspend` | super_admin | Suspend tenant |

### Users
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/users` | super_admin / owner | Create user |
| GET | `/api/v1/users` | Bearer | List users (tenant-scoped) |
| GET | `/api/v1/users/{id}` | Bearer | Get user |
| PATCH | `/api/v1/users/{id}` | owner+ | Update user |
| DELETE | `/api/v1/users/{id}` | owner+ | Disable user |

### Members
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/members` | staff+ | Create member |
| GET | `/api/v1/members` | Bearer | List / search members |
| GET | `/api/v1/members/{id}` | Bearer | Get member + subscription + payments |
| PATCH | `/api/v1/members/{id}` | staff+ | Update member |
| POST | `/api/v1/members/{id}/freeze` | staff+ | Freeze member |
| POST | `/api/v1/members/{id}/unfreeze` | staff+ | Unfreeze member |
| POST | `/api/v1/members/{id}/cancel` | owner+ | Cancel membership |

### Membership Plans
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/plans` | owner | Create plan |
| GET | `/api/v1/plans` | Bearer | List plans |
| PATCH | `/api/v1/plans/{id}` | owner | Update plan |
| DELETE | `/api/v1/plans/{id}` | owner | Deactivate plan |

### Subscriptions
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/subscriptions` | staff+ | Assign member to plan |
| GET | `/api/v1/subscriptions` | Bearer | List (filterable) |
| PATCH | `/api/v1/subscriptions/{id}` | staff+ | Update |

### Payments
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/payments` | staff+ | Record payment |
| GET | `/api/v1/payments` | Bearer | List (filterable by member, date range) |

### Leads
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/leads` | sales+ / staff+ | Create lead |
| GET | `/api/v1/leads` | Bearer | List / filter by status, source |
| GET | `/api/v1/leads/{id}` | Bearer | Get lead + activity feed |
| PATCH | `/api/v1/leads/{id}` | sales+ / staff+ | Update lead |
| POST | `/api/v1/leads/{id}/convert` | sales+ / staff+ | Convert to member |
| POST | `/api/v1/leads/{id}/activities` | sales+ / staff+ | Log activity |

### Dashboard
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/api/v1/dashboard` | owner+ | All dashboard metrics |
| GET | `/api/v1/dashboard/revenue` | owner+ | Revenue breakdown |
| GET | `/api/v1/dashboard/members` | Bearer | Member stats |
| GET | `/api/v1/dashboard/leads` | Bearer | Lead pipeline stats |

---

## 7. Frontend Stack

- **Framework:** React 19 + TypeScript + Vite (SPA, no SSR)
- **UI components:** shadcn/ui (Tailwind-based primitives)
- **Server state:** TanStack Query (React Query) — caching, invalidation, loading/error states, deduplication
- **Routing:** React Router
- **Testing:** Vitest + Testing Library
- **API client:** typed fetch wrapper (`lib/api-client.ts`) with auth token injection and 401 auto-redirect; feature-level `api.ts` files wrapped by TanStack Query hooks
- **Structure:** feature-based — each feature (`auth`, `tenants`, `members`, `dashboard`, `landing`) owns its pages, API calls, types, hooks, and tests
- **Auth:** `AuthProvider` context + `useAuth()` hook; token stored in `localStorage`; `ProtectedRoute` guards authenticated pages
- **Landing page:** Hebrew (`he-IL`), gym CRM positioning, "כניסה לפורטל" → login

### User flow
```
Landing (/) → Login (/login) → Dashboard (/dashboard)
                                  ├── /tenants (future)
                                  ├── /members (future)
                                  └── /leads (future)
```

See [`docs/frontend.md`](./frontend.md) for the full architecture and conventions.

---

## 8. Conventions

- **UUIDs** as primary keys everywhere
- **Timestamps** as `timestamptz`, stored in UTC, displayed in tenant timezone
- **Money** in cents (`int`), with a `currency` column (ISO 4217)
- **Soft delete**: not used in v1. Real deletes. Activity/audit logs in MongoDB preserve history.
- **Enums** as `text` with `CHECK` constraints, not Postgres `ENUM` types

---

## 9. Roadmap

1. **Phase 1 — Foundation** *(done)*: Tenants, Users, Auth, basic CRUD, Hebrew dashboard shell
2. **Phase 2 — Core CRM** *(now)*: Members, Membership Plans, Subscriptions, Payments
3. **Phase 3 — Growth**: Leads, Pipeline, Dashboard with real metrics
4. **Phase 4 — Flexibility**: Dynamic roles system (see `docs/features/roles.md`), owner settings page, per-tenant feature visibility, custom fields UI
5. **Phase 5 — Integrations**: Stripe/payment processing, CSV import/export
6. **Phase 6 — Advanced**: Class scheduling, trainer workflows, mobile, marketing automation, customizable dashboards

**Why Flexibility is Phase 4, not Phase 1:** The flexibility thesis (owner configures everything) is the product's core differentiator, but we can only design the permission grid after 2-3 real gym-scoped features exist to permission. Building it earlier means designing in the dark and rebuilding the grid as features land. In the meantime, the frontend's `permissions.canAccess(user, feature)` module uses a hardcoded baseline that will be swapped for backend-driven config — call sites won't change.

---

## 10. Open Questions

- **Pricing model** — per-gym flat fee, per-active-member, or tiered?
- **Self-serve signup** vs. sales-led onboarding for first gyms?
- **Email uniqueness** — global or per-tenant? (Affects login flow)
- **Billing integration** — import-only, or two-way sync with Stripe/GoCardless?
- **Notifications** — email/SMS to members for expiring plans, payment reminders?
