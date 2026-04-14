# Feature: Members

> **Status:** Planned. Not yet implemented. Plan for review before starting.
>
> This is the first gym-scoped feature and the entity every other Phase 2 feature depends on (Subscriptions → Members, Payments → Members, Leads convert into Members).

---

## Summary

**Member management** — the core of the CRM. Members are a gym's paying customers. They do **not** log into the system; they're records managed by gym staff.

A member belongs to exactly one tenant (gym). Every request is tenant-scoped via JWT.

### Where this fits

```
Tenant (a gym)                          Phase 1 — shipped
  ├── Users (staff who log in)          Phase 1 — shipped
  └── Members (gym's customers)         Phase 2 — this doc
       ├── Subscriptions (next)
       ├── Payments (next)
       └── (later) converted from Leads
```

Members are the first feature a gym owner actually uses on day one: "I just signed up, let me add my 80 existing members."

---

## User stories

1. **As a gym owner**, I can see all my members in one list — searchable by name, filterable by status.
2. **As a staff user**, I can add a new member with basic details (name, phone, optional email).
3. **As a staff user**, I can update a member's contact info, notes, and custom fields.
4. **As a staff user**, I can freeze a member (going on vacation, injured) — pauses their subscription without cancelling.
5. **As a staff user**, I can unfreeze a frozen member — reactivates their subscription.
6. **As an owner**, I can cancel a member — terminal state, preserves history for reporting.
7. **As a staff user**, I can view a member's profile: contact details, status, join date, notes, custom fields. (Subscription / payment history come when those features land.)
8. **As an owner**, I can see new-member count per month on the dashboard. (Replaces the current "בקרוב" placeholder.)

**Explicitly NOT in this feature (later):**
- Bulk CSV import — deferred, write-in manually for v1
- Member portal / self-service — members don't log in ever
- Subscription assignment — lives in the Subscriptions feature
- Payment recording — lives in the Payments feature

---

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | `/api/v1/members` | staff+ | 60/min/user | Create a member |
| GET | `/api/v1/members` | Bearer (tenant-scoped) | 60/min/user | List / search members |
| GET | `/api/v1/members/{id}` | Bearer (tenant-scoped) | 60/min/user | Get member by ID |
| PATCH | `/api/v1/members/{id}` | staff+ | 60/min/user | Partial update |
| POST | `/api/v1/members/{id}/freeze` | staff+ | 60/min/user | Freeze (pause subscription) |
| POST | `/api/v1/members/{id}/unfreeze` | staff+ | 60/min/user | Unfreeze |
| POST | `/api/v1/members/{id}/cancel` | owner+ | 60/min/user | Cancel (terminal) |

**`staff+`** = staff, sales, owner, super_admin. (Once dynamic roles land, this becomes `canAccess("members")` with write vs read distinction. For now, anyone who can see the feature can write.)

**`owner+`** = owner, super_admin only. Cancellation is destructive-ish and owner-gated.

**Tenant scoping is enforced in the service layer** — a staff user from gym A can never see/update a member from gym B, even with a forged UUID.

### List filters (query params on GET /members)

- `status` — filter by `active` | `frozen` | `cancelled` | `expired` (or multiple via `?status=active&status=frozen`)
- `search` — case-insensitive match on `first_name`, `last_name`, `phone`, `email`
- `limit` / `offset` — pagination (default 50, max 200)

---

## Domain (Layer 3)

### Entity

**`domain/entities/member.py`** — `Member` Pydantic model + `MemberStatus` StrEnum

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `tenant_id` | UUID | FK → tenants. Every request scoped by this. |
| `first_name` | str | Required |
| `last_name` | str | Required |
| `email` | str \| None | Optional — many gym members don't use email |
| `phone` | str | Required — primary contact in Israel |
| `date_of_birth` | date \| None | Optional |
| `gender` | str \| None | Optional, free text (not enum — respects flexibility principle) |
| `status` | MemberStatus | `active` / `frozen` / `cancelled` / `expired` |
| `join_date` | date | When they first joined the gym |
| `frozen_at` | date \| None | Set when status becomes `frozen` |
| `frozen_until` | date \| None | Optional — auto-unfreeze date |
| `cancelled_at` | date \| None | Set when status becomes `cancelled` |
| `notes` | str \| None | Free text, unbounded |
| `custom_fields` | dict[str, Any] | JSONB — per-tenant flexibility (see below) |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### `custom_fields` — the flexibility story

Following the project's flexibility thesis (`docs/spec.md` §1), members have a JSONB `custom_fields` column. Owners add whatever their gym tracks **as ad-hoc per-tenant data**:

```json
{
  "belt_color": "blue",
  "injury_notes": "left knee — avoid squats",
  "referral_source": "friend",
  "emergency_contact": "+972-50-123-4567",
  "trainer_preference": "morning",
  "is_veteran": true
}
```

**v1 scope:** the column exists and the backend stores/returns it unchanged. No UI for configuring which fields are exposed — that comes with the Owner Settings feature later. For now, custom fields are edited as raw JSON in the API, or as a future "notes-style" catch-all in the UI.

### What does NOT belong in `custom_fields`

`custom_fields` is **only** for free-form per-tenant data with no relational queries. Anything that you'd ever want to JOIN on, AGGREGATE over, or SHOW IN A DASHBOARD CHART is its own table.

| Use case | Where it lives |
|---|---|
| "Belt color", "injury notes", "referral source" — gym-specific tags on a single member | `members.custom_fields` JSONB |
| Class types this gym offers (Spinning, Pilates, CrossFit) | `classes` table — see [`classes.md`](./classes.md) |
| Class passes (10-punch card, unlimited monthly) per member | `class_passes` table — see [`classes.md`](./classes.md) |
| When a member checked in to a class | `attendance` table — see [`classes.md`](./classes.md) |
| A member's payments | `payments` table — own feature |
| A member's subscriptions | `subscriptions` table — own feature |

**Rule of thumb:** if the dashboard might ever filter, group, or count by it, it's a real table. If it's a sticky note about one specific person, it's a custom field.

### Pure logic methods

- `Member.is_active()` — True if status is `active`
- `Member.can_freeze()` — True if status is `active`
- `Member.can_unfreeze()` — True if status is `frozen`
- `Member.can_cancel()` — True if status is not already `cancelled`
- `Member.full_name()` — `"first_name last_name"`

### Exceptions

- `MemberNotFoundError` → 404
- `MemberAlreadyExistsError` → 409 (phone collision within tenant — see decisions)
- `InvalidMemberStatusTransitionError` → 409 (e.g. unfreezing an active member)
- `InsufficientPermissionsError` → 403 (already exists in `domain/exceptions.py`)

---

## Service (Layer 2)

**`services/member_service.py`**

```python
class MemberService:
    async def create(self, caller: User, data: MemberCreate) -> Member: ...
    async def get(self, caller: User, member_id: UUID) -> Member: ...
    async def list_for_tenant(
        self, caller: User, *,
        status: list[MemberStatus] | None = None,
        search: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Member]: ...
    async def update(self, caller: User, member_id: UUID, data: MemberUpdate) -> Member: ...
    async def freeze(self, caller: User, member_id: UUID, until: date | None = None) -> Member: ...
    async def unfreeze(self, caller: User, member_id: UUID) -> Member: ...
    async def cancel(self, caller: User, member_id: UUID) -> Member: ...
```

### Business rules (enforced in service)

- **Tenant scoping** — every method asserts `member.tenant_id == caller.tenant_id` (super_admin bypasses). A staff user reading by UUID gets 404 if the member belongs to another gym (not 403 — we don't leak existence).
- **Status transitions** — enforced via `can_freeze()`/`can_unfreeze()`/`can_cancel()` on the entity. Invalid transitions raise `InvalidMemberStatusTransitionError` → 409.
- **Phone uniqueness** — within a tenant, phone must be unique. Prevents accidental duplicate entries during manual data entry. Across tenants, same phone is fine (one person may be a member of two gyms).
- **`cancel` is owner+ only** — destructive-ish, preserves data. `InsufficientPermissionsError` → 403 for non-owners.
- **Join date default** — if omitted, service sets `join_date = today` in the tenant's timezone.
- **Trial period limits** — new tenants may be restricted by `tenant_config.limits.max_members`. Enforcement via a pre-check on `create`; when limit reached → 402 Payment Required. (Stub for v1 — all trial tenants get 1000 members, same as default plan. Real enforcement comes with billing.)

---

## Adapter (Layer 4)

### Database model

File: `adapters/storage/postgres/member/models.py`

Table: `members`

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` |
| tenant_id | uuid | NOT NULL, FK → `tenants.id` ON DELETE CASCADE |
| first_name | text | NOT NULL |
| last_name | text | NOT NULL |
| email | text | nullable |
| phone | text | NOT NULL |
| date_of_birth | date | nullable |
| gender | text | nullable |
| status | text | NOT NULL, CHECK (`active`/`frozen`/`cancelled`/`expired`), default `'active'` |
| join_date | date | NOT NULL, default `current_date` |
| frozen_at | date | nullable |
| frozen_until | date | nullable |
| cancelled_at | date | nullable |
| notes | text | nullable |
| custom_fields | jsonb | NOT NULL, default `'{}'` |
| created_at | timestamptz | NOT NULL, default `now()` |
| updated_at | timestamptz | NOT NULL, default `now()`, auto-update |

**Indexes:**
- `idx_members_tenant` on `(tenant_id)` — every query filters by tenant
- `idx_members_tenant_status` on `(tenant_id, status)` — dashboard queries like "active members"
- `uniq_members_tenant_phone` UNIQUE on `(tenant_id, phone)` — phone collision within gym
- GIN index on `custom_fields` (optional, add if search-by-custom-field performance matters later)

**FK `ON DELETE CASCADE`** — deleting a tenant deletes all its members. Matches the "every entity belongs to a tenant" rule. (We don't actually hard-delete tenants today — `status=cancelled` is soft-delete — so this is a safety net.)

### Repository methods

File: `adapters/storage/postgres/member/repositories.py`

- `create(tenant_id, data) -> Member` — INSERT, catches IntegrityError → MemberAlreadyExistsError (phone collision)
- `find_by_id(member_id) -> Member | None` — SELECT by PK (does NOT filter by tenant — that's service's job, so a super_admin impersonation flow can still read)
- `find_by_tenant_and_phone(tenant_id, phone) -> Member | None`
- `list_for_tenant(tenant_id, *, status, search, limit, offset) -> list[Member]` — SELECT with filters
- `count_for_tenant(tenant_id, status: MemberStatus | None) -> int` — for dashboard and limits check
- `update(member_id, **fields) -> Member` — partial UPDATE

### Migrations

- `0005_create_members.py` — create `members` table + indexes + check constraints

---

## API (Layer 1)

### Routes

File: `api/v1/members/router.py`

Thin route handlers — parse request, call service, format response. No business logic.

- `POST /` — parse `CreateMemberRequest`, call `service.create`, return 201 `MemberResponse`
- `GET /` — parse query filters, call `service.list_for_tenant`, return `list[MemberResponse]`
- `GET /{id}` — call `service.get`, return `MemberResponse`
- `PATCH /{id}` — parse `UpdateMemberRequest`, call `service.update`, return `MemberResponse`
- `POST /{id}/freeze` — parse optional `{ until: date }`, call `service.freeze`, return `MemberResponse`
- `POST /{id}/unfreeze` — call `service.unfreeze`, return `MemberResponse`
- `POST /{id}/cancel` — call `service.cancel`, return `MemberResponse`

### Schemas

File: `api/v1/members/schemas.py`

**CreateMemberRequest**
```json
{
  "first_name": "Dana",
  "last_name": "Cohen",
  "phone": "+972-50-123-4567",
  "email": "dana@example.com",
  "date_of_birth": "1990-05-15",
  "gender": "female",
  "join_date": "2026-04-12",
  "notes": "Prefers morning sessions",
  "custom_fields": {"referral_source": "walk_in", "emergency_contact": "+972-52-999-8888"}
}
```
Only `first_name`, `last_name`, `phone` are required. Server fills `join_date` with today if omitted.

**UpdateMemberRequest** — same as Create but all fields optional.

**FreezeRequest** (optional body for `POST /freeze`)
```json
{ "until": "2026-05-12" }
```

**MemberResponse** — full member object, same shape as entity.

### Dependencies used

- `get_current_user` — JWT validation, extracts `tenant_id`
- `require_canaccess("members")` — NEW dependency. For now it just checks role ≠ super_admin (who shouldn't be poking gym data directly). Backend mirror of frontend's `canAccess`. When dynamic roles land this becomes a real check.
- `require_owner_or_super_admin` — gate for `cancel`
- `api_rate_limit` — 60/min per user

---

## Frontend

### Types

`features/members/types.ts`:

```ts
export type MemberStatus = "active" | "frozen" | "cancelled" | "expired"

export interface Member {
  id: string
  tenant_id: string
  first_name: string
  last_name: string
  email: string | null
  phone: string
  date_of_birth: string | null
  gender: string | null
  status: MemberStatus
  join_date: string
  frozen_at: string | null
  frozen_until: string | null
  cancelled_at: string | null
  notes: string | null
  custom_fields: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateMemberRequest { /* first_name, last_name, phone required, rest optional */ }
export interface UpdateMemberRequest { /* all optional */ }
```

### API functions

`features/members/api.ts`:

```ts
export function listMembers(filters?: { status?: MemberStatus[]; search?: string; limit?: number; offset?: number }): Promise<Member[]>
export function getMember(id: string): Promise<Member>
export function createMember(data: CreateMemberRequest): Promise<Member>
export function updateMember(id: string, data: UpdateMemberRequest): Promise<Member>
export function freezeMember(id: string, until?: string): Promise<Member>
export function unfreezeMember(id: string): Promise<Member>
export function cancelMember(id: string): Promise<Member>
```

Each function gets JSDoc with `@param`, `@returns`, `@throws ApiError(...)`.

### Hooks

`features/members/hooks.ts`:

Standard pattern — `useMembers()`, `useMember(id)`, `useCreateMember()`, `useUpdateMember()`, `useFreezeMember()`, `useUnfreezeMember()`, `useCancelMember()`. Every mutation invalidates `["members"]`.

### Pages & components

- **`MemberListPage.tsx`** — route `/members`, gated by `RequireFeature feature="members"`
  - Header: "מנויים" + "הוספת מנוי" button (opens create dialog)
  - Search bar (debounced, updates query params)
  - Status filter chips (All / Active / Frozen / Cancelled / Expired)
  - Table: Name, Phone, Status badge (color-coded), Join date, "פעולות" dropdown
  - Row actions per status:
    - active: Edit, Freeze, Cancel
    - frozen: Edit, Unfreeze, Cancel
    - cancelled: View only (no mutations)
    - expired: Edit, Reactivate (unfreeze)
  - Cancel opens `ConfirmDialog` (reused from tenants)
  - Edit opens modal with `MemberForm`
- **`MemberForm.tsx`** — shared between create and edit
  - Required: first_name, last_name, phone
  - Optional: email, DOB, gender, join_date, notes
  - `custom_fields` — for v1, a "notes-style" JSON textarea (raw JSON). Real UI for configurable fields lands with Owner Settings feature.
- **Hebrew error humanizer** — `humanizeMemberError()` added to `lib/api-errors.ts`:
  - 409 phone collision → "מנוי עם מספר טלפון זה כבר קיים"
  - 409 invalid status transition → "לא ניתן לבצע פעולה זו בסטטוס הנוכחי"
  - 422 → generic validation

### Permissions

Add `"members"` to the `Feature` union in `features/auth/permissions.ts` (already there — was placeholder, now becomes real). Update `BASELINE`:
- owner: already has `"members"` (no change)
- staff: add `"members"` — they need day-to-day member management
- sales: add `"members"` — they need to see members to convert leads
- super_admin: still platform only, no `"members"`

Route: wrap `/members` with `<RequireFeature feature="members" />` in `app/App.tsx`.

Sidebar: uncomment the members entry in `NAV_ITEMS`.

### Dashboard wire-up

Swap the "מנויים פעילים" placeholder in `GymDashboard.tsx` for a real count. Add a new hook `useMemberCount({ status: "active" })` that hits `GET /members?status=active&limit=1` and reads the count from a response header (or add a dedicated endpoint — decide during implementation).

---

## Tests

### Backend

| Type | File | What |
|------|------|------|
| Unit | `tests/unit/test_member_entity.py` | Entity pure logic, `can_freeze()`/`can_unfreeze()`/`can_cancel()`, `full_name()`, required fields |
| Unit | `tests/unit/test_member_service.py` | Mocked repo; tenant scoping, permission checks, status transitions, phone collision |
| Integration | `tests/integration/test_member_repo.py` | Repo against real Postgres — create, filter by status/search, unique(tenant_id, phone) constraint |
| E2E | `tests/e2e/test_members.py` | Full HTTP: create, list, filter, freeze/unfreeze/cancel, 403 for other-tenant member, 404 for missing, 409 for phone collision |

### Frontend

| File | Tests |
|------|-------|
| `features/members/api.test.ts` | Each function hits the right endpoint with the right body |
| `features/members/MemberListPage.test.tsx` | Renders, filters work, row actions dispatch right mutation |
| `features/members/MemberForm.test.tsx` | Validation, submit shape, edit prefills |
| `features/auth/permissions.test.ts` | Add cases: staff/sales now have `"members"` in baseline |
| `lib/api-errors.test.ts` | `humanizeMemberError` for 409 phone, 409 transition, 422, generic |

---

## Decisions (to approve / discuss)

1. **Members don't log in.** They have no `hashed_password`, no `users` row. Gym members are records, not user accounts. Matches the spec.
2. **Phone is required, email is optional.** In Israel, phone is the universal contact. Many older members don't use email. Unique within tenant.
3. **Phone uniqueness within tenant only.** A person can be a member of two gyms — same phone, different `tenant_id`. Enforced via `UNIQUE (tenant_id, phone)`.
4. **Status enum: active / frozen / cancelled / expired.** Matches spec. `expired` is set by a scheduled job later when subscription ends; not settable via API.
5. **No subscription on create.** Creating a member is separate from giving them a plan. A just-created member has status `active` but no subscription — on the dashboard they count as "active members" but contribute `0` to MRR. This matches reality: gyms log the person before setting up billing.
6. **`custom_fields` as JSONB, no UI for v1.** API accepts/returns it unchanged. Owners can set custom fields via API or a raw-JSON textarea. Proper UI comes with Owner Settings.
7. **`gender` as free text, not enum.** Flexibility principle — different gyms use different options (some want `male/female`, some want `male/female/non-binary/prefer-not-to-say`). Owner-configurable enum lives in tenant config (future).
8. **Cancel is owner+ only.** Staff can freeze (reversible), only owner can cancel (terminal-ish). Prevents accidental data loss by a new staff member clicking the wrong button.
9. **Soft delete via `cancelled` status.** No hard delete. Preserves churn history for reporting.
10. **No bulk CSV import for v1.** Ship manual-entry first. Bulk import is its own feature with its own edge cases (dedup, validation, partial failure).
11. **No member portal for v1.** Members don't log in. If we add this later, it's a separate auth flow with a different token type — out of scope here.
12. **Date of birth separate from age.** Store DOB, compute age if needed. Birthday reports are a nice dashboard widget later.
13. **Israel timezone for `join_date` default.** Service uses `tenant.timezone` when setting "today". Gyms don't close at midnight UTC.

---

## Migration plan

Ship as one PR (or 2 — backend then frontend):

1. **Backend PR** — migration, entity, repo, service, routes, schemas, tests. Ship behind `RequireFeature` on frontend so non-existent route doesn't show yet.
2. **Frontend PR** — types, api, hooks, pages, form, tests. Enable sidebar link and route guard at the end.

OR one unified PR if the scope stays tight.

---

## Open questions (for you to decide)

1. **Should cancelling a member auto-cancel their subscription?** Subscriptions don't exist yet, so defer — but flag the hook point in `MemberService.cancel` for when Subscriptions land.
2. **Should `custom_fields` have a schema at the tenant level (allowlist of keys)?** For v1 no — store anything. Later, Owner Settings defines allowed fields. This means we don't break existing data when schema is added.
3. **`gender` — free text or enum today?** My vote: free text. Owner-configurable enum when Owner Settings lands.
4. **`expired` status — who sets it?** A nightly Celery task scans subscriptions and flips members whose last subscription expired. Defer the task until Subscriptions are built; the column exists from day 1.
5. **Should there be a `DELETE /members/{id}` for truly removing a record (GDPR)?** Yes eventually — GDPR "right to be forgotten" requires hard delete on request. Out of scope for v1 but put in TODO.
6. **Dashboard count query — header vs dedicated endpoint?** Leaning dedicated: `GET /members/stats` returns `{ active, frozen, cancelled, expired, new_this_month }`. Cleaner than scraping headers. Decide during implementation.

---

## Related docs

- [`spec.md`](../spec.md) §3.4 — product spec for members
- [`tenants.md`](./tenants.md) — parent entity, same pattern
- [`users.md`](./users.md) — sibling entity (staff who manage members)
- [`roles.md`](./roles.md) — when dynamic roles land, member permissions become owner-configurable
- [`../skills/build-backend-feature.md`](../skills/build-backend-feature.md) — step-by-step recipe
- [`../skills/build-frontend-feature.md`](../skills/build-frontend-feature.md) — frontend recipe
