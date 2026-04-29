# DopaCRM — Product Specification

> Living document. Last updated: 2026-04-11.
>
> This is the source of truth for what DopaCRM does, who it serves, and how the domain is modeled. Architecture and coding conventions live in `CLAUDE.md` and `docs/standards/`. Per-feature implementation details live in `docs/features/`. Cross-feature business rules (attribution, pro-ration, state machines, immutability) live in [`crm_logic.md`](./crm_logic.md).

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

**Tenant config** (feature flags, operational limits, and plan-specific settings) — originally planned for a Mongo `tenant_configs` collection, but revised: lives in a JSONB column on the `tenants` table (or a dedicated `tenant_configs` Postgres table if it grows). Same shape, same seed-from-saas-plan flow, but keeps tenant config transactional with the rest of the tenant row. Example shape:

```json
{
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

Prospective members moving through a sales pipeline. **Gated feature** — OFF by default for new tenants; super_admin flips it per gym. Some gyms run on word-of-mouth and have no use for a pipeline.

**Stored in:** PostgreSQL (`leads` table) + `lead_activities` table for the activity feed.

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
| assigned_to | uuid | FK → `users`. Nullable. Routing/reporting only — sales sees all leads in tenant. |
| notes | text | Nullable |
| lost_reason | text | Nullable. Set when status = `lost`. Free text with autocomplete from tenant's recent reasons. |
| converted_member_id | uuid | FK → `members`. Set when status = `converted` |
| custom_fields | jsonb | Reserved for per-tenant fields; no UI in v1 |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Activity types (v1):** `call`, `email`, `note`, `meeting`, `status_change`. The first four are user-logged; `status_change` is auto-generated on every transition. Activities are append-only — no edit, no delete.

**Pipeline stages:**
```
new → contacted → trial → converted   (terminal — must go through convert endpoint)
                       ↘ lost          (reopen path → contacted)
```

**Business rules:**
- Converting a lead is **atomic** — single endpoint creates a `Member` (auto-filled) + first `Subscription` (plan picker) + flips `lead.status='converted'` + writes `status_change` activity, all in one Postgres transaction.
- Lost leads can be reopened (status back to `contacted`); historical lost reason is preserved in the activity row but the column is cleared.
- Drag-to-converted is **not** available via simple status PATCH — the convert endpoint is the only path (it requires a plan).
- Lead source tracking for "where do our members come from?" reporting.

**Permissions:** owner / sales: full CRUD + convert. staff: read-only (so check-in staff can spot a walk-in's lead history). coach: no access. super_admin: platform.

See [`docs/features/leads.md`](features/leads.md) for the full spec — entity, service rules, API, UI sketch, tests, migration plan.

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

Gym owners will be able to choose which widgets to show, set date ranges, and arrange layout. Config stored in a Postgres `user_dashboard_configs` table (originally planned for Mongo — revised, see §4):

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

### 3.10 Coaches & Payroll

Coaches are the gym's trainers — the people who teach classes. DopaCRM tracks them as first-class entities with per-class pay rules, so the owner can ask the most basic operational question: *"how much do I owe this month?"*

**Stored in:** PostgreSQL (`coaches` + `class_coaches` tables; `class_entries.coach_id` column). Full spec in [`features/coaches.md`](./features/coaches.md).

**Key concepts:**

- **A coach is not a user by default.** Coaches are their own table; optionally linked to a `users` row when the owner wants them to log in. A coach without a user row exists on the payroll, nothing more. A logged-in coach sees a read-only baseline: their classes, their attendance rosters, their earnings.
- **Pay rules live on the (coach, class) link.** The same coach can be "head of boxing at ₪50 per attendee" AND "assistant in wrestling at ₪30 per session". Three pay models: `fixed` (monthly salary, pro-rated), `per_session`, `per_attendance`.
- **Weekday teaching pattern.** Each (coach, class) link holds an array of weekdays. At check-in, the server looks up which coach taught based on `entered_at.weekday()` and stamps `class_entries.coach_id`. Immutable history — rate changes don't rewrite past payroll.
- **Substitutions** (coach sick, someone covers) will be edited from the future Schedule week view, not inline at check-in. Until Schedule ships, an admin endpoint `POST /attendance/{id}/reassign-coach` handles mis-attributions.
- **Coaches add a role.** `users.role` gains `coach` as a system-defined role. Owner + super_admin keep their current powers; dynamic roles (Phase 4) will let the owner customize what each coach sees per-tenant.

**Business rules that cross features** — attribution, pay pro-ration, what counts as an "effective" entry — are captured in [`crm_logic.md`](./crm_logic.md) so Coaches, Payments, Attendance, and future Schedule stay in sync.

**Roadmap slot:** Coaches is part of Phase 3 (Operations) alongside Payments and Leads. See §9 below.

---

### 3.11 Schedule

Weekly calendar of when classes actually run, who teaches them, and how substitutions / cancellations are captured. **Upgrades coach attribution** from the v1 weekday pattern (per `class_coaches`) to per-session truth — when an attendance is recorded, the system looks up today's scheduled session for that class and stamps `class_entries.session_id` + `coach_id = session.head_coach_id`. Weekday attribution remains as the fallback for drop-ins with no scheduled session.

**Stored in:** PostgreSQL (`class_schedule_templates` + `class_sessions` tables; `class_entries.session_id` column). Full spec in [`features/schedule.md`](./features/schedule.md).

**Key concepts:**

- **Templates + materialized sessions.** Owner creates a recurring template ("boxing, Sun+Tue, 18:00–19:00, head coach David"). On create, the backend materializes **8 weeks of concrete sessions**. A Celery beat job extends the horizon nightly so there's always ~8 weeks of visibility.
- **Two coach slots per session.** `head_coach_id` drives payroll attribution; `assistant_coach_id` is informational. Not an N-coach array — 99% head+assistant, cleaner data model, single-table join.
- **Status: `scheduled` or `cancelled`.** "Completed" is derived (`ends_at < now()`). Cancelled is terminal; uncancelling = create a new session.
- **Individual + bulk edits.** Owner can cancel / swap coach on one session, or bulk-apply across a date range (2-week vacation scenario). Manual edits set `is_customized=TRUE` so template changes don't stomp owner choices.
- **Cancellation = no pay** for `per_session` coaches. Per-session pay math upgrades from the v1 "distinct days with ≥1 entry" proxy to `count(status='scheduled' AND head_coach_id=coach)`.
- **Feature-gated.** OFF by default for new tenants (see §3.12). If off, attendance attribution skips the session lookup entirely — the v1 weekday path stays.

Cross-cutting rules for session-based attribution, cancellation-pay semantics, and the upgraded per-session pay math live in [`crm_logic.md`](./crm_logic.md).

**Roadmap slot:** Phase 3, between Coaches and Payments. See §9.

---

### 3.12 Feature Flags

Per-tenant on/off switches for **advanced features** (Coaches, Schedule, future modules). Lets super_admin match each gym's actual operating model instead of forcing every feature on everyone — a solo-operator boxing gym doesn't need payroll tracking, and a yoga studio without recurring classes doesn't need a weekly calendar.

**Stored in:** `tenants.features_enabled JSONB`, shape `{"coaches": true, "schedule": false}`. Full spec in [`features/feature-flags.md`](./features/feature-flags.md).

**Today:**
- Super_admin toggles via `PATCH /api/v1/tenants/{id}/features` — visible on the `/tenants/{id}` page.
- **OFF by default** for new tenants (minimal onboarding experience).
- Existing tenants backfilled with `{"coaches": true}` so nothing regresses.
- Gate enforced at the service layer (`FeatureDisabledError` → 403) + the frontend (`canAccess(user, feature, tenantFeatures)` skips baseline grant if gate is off).

**What's gated vs ungated:**

| Ungated (always on) | Gated (per-tenant) |
|---|---|
| dashboard, members, classes, plans, subscriptions, attendance, users | coaches, schedule (+ future leads, payments, reports when shipped) |

**Where it's headed:** This mechanism is the first piece of Phase 4 flexibility. Owner self-service (via a Settings page) is a one-line role-gate change when that UI lands. Dynamic roles (`docs/features/roles.md`) build *on top* of feature flags — the flag decides if a feature is available at all; roles decide which users can use it.

---

## 4. Data Architecture

### PostgreSQL (primary — transactional entities)

All core business entities: `tenants`, `saas_plans`, `users`, `members`, `membership_plans`, `subscriptions`, `payments`, `leads`, `refresh_tokens`, `classes`, `class_entries`, `coaches`, `class_coaches`, `class_schedule_templates`, `class_sessions`.

JSONB columns for per-entity flexibility: `membership_plans.custom_attrs`, `members.custom_fields`, `coaches.custom_attrs`, `tenants.features_enabled`.

### MongoDB — provisioned but currently unused

The original design reserved Mongo for `tenant_configs`, activity logs, audit trails, lead activities, integration payloads. **As of 2026-04-16, none of these are live.** Every case we've hit is better served by Postgres with either a real table or a JSONB column — FK integrity, transactions, and GROUP BY reporting all matter more than schema-less flexibility at our scale.

**Default for new features: Postgres.** Don't add Mongo collections unless a use case genuinely requires it (truly free-shape third-party webhook archives, massive append-only event streams). Apply this rubric:

- Data FKs into Postgres entities? → Postgres.
- Shape is mostly uniform? → Postgres.
- Ingestion rate is modest (single-digit thousands / day)? → Postgres handles it.

If Mongo stays empty through Phases 2-3, it gets removed from the stack in a later cleanup.

### Redis

- Rate limit counters
- JWT blacklist (logout invalidation)
- Config cache (when/if tenant config becomes a hot path)

---

## 5. Multi-tenancy

- **Shared schema** with `tenant_id` on every table (not schema-per-tenant)
- Every query is scoped by `tenant_id`, extracted from JWT
- Tenant isolation is enforced at the **service layer** — services always receive `tenant_id` and pass it to repositories
- Redis caching is namespaced by `tenant_id`
- **One tenant = one gym** in the current model. All fields on `tenants` (slug, name, address, phone, email) describe a single physical location.

### Multi-location gyms — v1 workaround, future consolidation

A chain with 3 branches (e.g. Holmes Place TLV + Haifa + Ramat Gan) onboards today as **3 separate tenants** — each with its own members, staff, classes, plans, billing. Full data isolation between branches, which is actually the safer default (TLV's staff shouldn't accidentally see Haifa's members).

**What's deferred until a real multi-location customer asks:**

- **Company-level parent tenant.** A `parent_tenant_id` FK on `tenants` would group the 3 branches under one "company" tenant for consolidated reporting and a "company owner" role with read access across branches.
- **Cross-tenant dashboards.** "Total revenue across all branches" roll-up.
- **Shared member records.** Today a member training at both TLV and Haifa is two rows. Deduplication via `company-level members` is deferred.
- **Unified billing.** Possibly consolidated to the parent tenant, or kept per-branch.

**Why defer:** the 100 possible "consolidated" features are ambiguous without a real customer telling us which they actually need. The workaround (N tenants) is shippable today and already gives proper data isolation. When a real multi-location customer arrives, their specific needs inform the design.

**What's not blocked:** nothing in the current schema prevents adding `parent_tenant_id` later — it's a non-breaking migration.

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
- **Soft delete via status flags** (members, plans, tenants → `status=cancelled`/`is_active=false`). No hard deletes in v1 — activity/audit logs (Postgres tables) preserve history.
- **Enums** as `text` with `CHECK` constraints, not Postgres `ENUM` types

---

## 9. Roadmap

1. **Phase 1 — Foundation** *(done)*: Tenants, Users, Auth, basic CRUD, Hebrew dashboard shell
2. **Phase 2 — Core CRM** *(done)*: Members, Classes, Membership Plans, Subscriptions, Attendance (check-in)
3. **Phase 3 — Operations** *(now)*:
   - Coaches & payroll *(shipped)*
   - **Schedule + Feature Flags** *(shipped)* — weekly calendar, templates, materialized sessions, cancellation, substitutions; tenant-level feature gating
   - **Leads + Pipeline** *(in progress)* — gated feature, OFF by default
   - Payments
   - Dashboard with real metrics
4. **Phase 4 — Flexibility**: Dynamic roles system (see `docs/features/roles.md`), owner-facing Settings page (flips feature flags + role grants), custom fields UI, private 1-on-1 workouts
5. **Phase 5 — Integrations**: Stripe/payment processing, CSV import/export
6. **Phase 6 — Advanced**: Trainer mobile app, marketing automation, customizable dashboards

**Ordering within Phase 3.** Coaches *(shipped)* → **Schedule + Feature Flags** *(shipped)* → **Leads** *(in progress)* → Payments → Dashboard metrics. Schedule followed Coaches because it upgrades the weekday-based attribution to per-session truth (details in `docs/features/schedule.md` §"Attribution upgrade"). Feature Flags shipped *with* Schedule because both Coaches and Schedule need tenant-level on/off — Coaches got a backfill flag in the same migration. Leads precedes Payments because Leads has no dependency on Payments and the Dashboard wire-up at the end of the phase wants Leads metrics too. Dashboard is last because it's a consumer of every upstream feature's metrics.

**Why Flexibility is Phase 4, not Phase 1:** The flexibility thesis (owner configures everything) is the product's core differentiator, but we can only design the permission grid after 2-3 real gym-scoped features exist to permission. Building it earlier means designing in the dark and rebuilding the grid as features land. **The Feature Flags mechanism shipping in Phase 3 is the first concrete piece of that vision** — tenant-level on/off, super_admin-controlled today, owner-controlled when the Settings page lands. In the meantime, the frontend's `permissions.canAccess(user, feature, tenantFeatures)` module uses a hardcoded baseline that will be swapped for backend-driven config — call sites won't change.

---

## 10. Open Questions

- **Pricing model** — per-gym flat fee, per-active-member, or tiered?
- **Self-serve signup** vs. sales-led onboarding for first gyms?
- **Email uniqueness** — global or per-tenant? (Affects login flow)
- **Billing integration** — import-only, or two-way sync with Stripe/GoCardless?
- **Notifications** — email/SMS to members for expiring plans, payment reminders?
