# Feature: Leads

> **Status:** Planned. Spec for review — not yet implemented.
>
> **Order:** Build AFTER Schedule (shipped). Leads ships AHEAD of
> Payments — the Dashboard wire-up at the end of Phase 3 wants Leads
> metrics, and Leads has no dependency on Payments. Ships as a **gated
> feature, OFF by default** for new tenants — owners flip it on when
> they want a sales pipeline (some gyms run purely on word-of-mouth and
> don't need one).
>
> **What this is:** the gym's sales pipeline. Prospective members move
> through `new → contacted → trial → converted` (or `lost`); every
> touchpoint is logged; "convert" creates a real `Member` + first
> `Subscription` in one transaction.

---

## Summary

Until now the gym CRM has been about people who already pay — members,
subscriptions, attendance, coaches, schedule. Leads is the first
feature about people who **don't pay yet**. It answers Monday-morning
questions like *"who walked in last week and didn't sign up? Did Yael
follow up with the Tuesday trial people? Why are we losing 30% of our
walk-ins after the trial?"*

Concretely, this feature builds:

- **A `leads` table** — prospect records: name, phone, optional email,
  source, current pipeline status, who's assigned to follow up,
  free-text notes, and (when converted) a FK to the resulting member.
- **A `lead_activities` table** — append-only log of touchpoints: each
  call, email, in-person note, scheduled meeting, plus an
  auto-generated `status_change` row on every pipeline transition. The
  feed is the lead's history; nothing is edited or deleted.
- **A `/leads` page** — Kanban board, one column per pipeline stage,
  cards drag between columns. Built for the "where am I in my week?"
  glance.
- **A lead detail page** — full activity timeline + inline "+ call /
  + email / + note / + meeting" forms + a single "המר למנוי" (convert
  to member) action that opens a plan picker.
- **Convert flow** — atomic: creates `Member` (auto-filling
  first_name, last_name, phone, email from the lead), creates the
  first `Subscription` against a plan the user picks, sets
  `lead.converted_member_id` and flips status to `converted`. All in
  one transaction — partial state is impossible.
- **Lost-reason capture** — free text with autocomplete from the
  tenant's recent lost reasons, so "too expensive" stops being typed
  six different ways while still letting an owner write something
  brand new.
- **Permission layering** — owner full; sales sees **all** leads in
  the tenant + edits; staff read-only (so check-in staff can spot a
  walk-in's lead history); coach: no access. Sales is intentionally
  not partitioned by `assigned_to` — gyms tend to have 1–2 sales
  people who cover for each other.
- **Feature flag** — `tenants.features_enabled.leads`. OFF by default;
  super_admin flips it. Service-layer guard returns 403
  `FEATURE_DISABLED` on every endpoint when off; sidebar link hides;
  Dashboard "leads in pipeline" widget hides.

---

## Why it's a separate feature (not folded into Members)

- **Different lifecycle.** A member exists once they pay. A lead may
  never become a member. Mixing them muddles "active members" —
  every dashboard query has to filter `WHERE not_a_lead`.
- **Different write pattern.** Members get created once and updated
  rarely; leads accrete activity rows daily and flip status often.
  Separate tables = separate access patterns = separate indexes.
- **Different permission gate.** Sales role's job is leads. Today
  sales also has access to members (so they can see existing-member
  data when judging conversion potential), but it's the leads
  feature where sales does its writes. Owner-configurable down the
  road.
- **Different feature-flag posture.** Some gyms (small co-ops,
  private studios) don't track leads at all. The flag lets us ship
  the table + UI without forcing it on tenants who have no use for
  it.

---

## Where this sits in Phase 3

```
  Phase 2 (Core CRM) — shipped:
    Members / Classes / Plans / Subscriptions / Attendance

  Phase 3 (Operations):
    Coaches                 ✓ shipped
    Schedule + Feature Flags ✓ shipped
    Leads                    ← THIS DOC
    Payments                 (after Leads — independent)
    Dashboard metrics wiring (last — consumes every upstream feature)

  Phase 4 (Flexibility):
    Dynamic roles → owner configures lead permissions per role
    Custom pipeline stages → not v1 (see §"Decisions")
    Custom lead fields → JSONB column reserved, no UI yet
```

Leads is Phase 3 because it's the second-half story of a gym's
operations: getting people in the door (sales) is just as load-bearing
as keeping them happy once they're in (members + classes). It comes
**after** Schedule because Schedule answers "what does the gym look
like this week?" — and the trial activity on a lead often references a
real session ("booked her for Tuesday 18:00 boxing").

---

## User stories

1. **As an owner**, I open `/leads` and see a Kanban — `חדש`,
   `נוצר קשר`, `ניסיון`, `הומר`, `אבוד`. Each column shows a stack of
   cards: name, phone, source, days-in-stage. I see at a glance that
   12 leads are in `נוצר קשר` and only 3 are in `ניסיון` — the funnel
   is leaking between contact and trial.
2. **As a sales rep**, I drag Yael's card from `חדש` to `נוצר קשר`
   after calling her. The status flips, an auto-`status_change`
   activity row is logged with my user-id, and I'm done in one motion
   — no separate "log activity" click.
3. **As a sales rep**, I open Yael's card and click `+ שיחה`. A small
   form appears inline: free-text note ("Interested in boxing, no
   evenings, free Sundays"). Submit. The activity timeline updates
   without a page reload.
4. **As a sales rep**, Yael walks in for her trial Tuesday. After
   class I open her card and click `+ פגישה`, log "completed trial,
   loved it, ready to sign up." Then I click `המר למנוי`, pick the
   "חודשי בלתי מוגבל" plan from the dropdown, hit save. Behind the
   scenes a `Member` row is created with her info pre-filled, a
   `Subscription` is opened against the plan, the lead is marked
   `converted` with a FK to the new member. One click, four writes,
   one transaction.
5. **As a sales rep**, the call goes badly — Yael says "too
   expensive". I drag her card to `אבוד`. A small dialog asks for the
   reason. As I type "יקר" the autocomplete suggests "יקר מדי" (the
   tenant's most-used lost reason this month). I pick it; the lead
   moves; the activity logs `status_change` with `reason: "יקר מדי"`.
6. **As an owner**, I open the lost lead from yesterday. The status
   says `אבוד`. I click `החזר לפיפליין` (reopen) → status back to
   `נוצר קשר`. An auto-`status_change` row is logged. Lost is not
   terminal.
7. **As staff** at check-in, I'm looking up a member who isn't in the
   system. I notice a "Yael Cohen" lead from 2 weeks ago. I click
   through to the lead detail (read-only for me) — yes, this is the
   same person. I tell sales to convert her instead of me creating a
   duplicate member.
8. **As an owner**, on the dashboard I see "12 leads in pipeline" and
   "27% conversion rate this month". The widgets only render because
   Leads is enabled for my tenant; gyms without the flag see no Leads
   widgets.
9. **As super_admin**, I onboard a new gym. The Leads flag is OFF by
   default. The owner asks for it; I open `/tenants/:id`, the
   Features section, tick `leads`. The tenant immediately gets the
   sidebar link, the page, and the dashboard widgets.

---

## Decisions (baked in from the back-and-forth)

### 1. Pipeline stages — fixed, hardcoded

`new → contacted → trial → converted` (with `lost` as a side state
reachable from any non-converted stage).

Rationale: Phase 3 is for shipping working flows — not for
configurability. Custom pipeline stages **are** on the Phase 4
roadmap (owner-configurable along with roles, custom fields,
workflows). Until the configurability infrastructure exists, fixed
stages let us:

- Build a real Kanban with known column count
- Wire dashboard widgets to specific status names
- Define a tight state machine (see §3 below)

When dynamic stages land, the migration path is `tenant_pipelines`
table per tenant; existing tenants get a "default pipeline" row with
these 5 stages and existing data is preserved.

### 2. Sales rep visibility — sees ALL leads in the tenant

Not partitioned by `assigned_to`. Most gyms have 1–2 sales people who
cover for each other; partitioning creates a worse UX (a sales rep
can't pick up a colleague's leads when they're sick). Owner sees all
leads anyway.

`assigned_to` exists as a column for **routing and reporting** ("how
many leads is each rep handling? who closed the most this month?")
but is not used as an authorization filter today.

When dynamic roles land in Phase 4, an owner can flip a "sales sees
only assigned" toggle per tenant.

### 3. Trial is just a status — no Subscription side-effect

Moving a lead to `trial` is a pipeline state change and nothing else.
We do NOT auto-create a Subscription for the trial. We do NOT block a
class check-in on the trial lead's name.

Trial bookings are recorded as **`meeting` activity rows** with a
free-text note like *"trial booked for Tuesday 18:00 boxing"*. If the
gym wants the trial-attender to actually walk into a class, the
existing `record_entry` flow with a Member row covers it once
converted. For unconverted trial-attenders (still a lead), the gym
counts the visit informally — this is intentional. Adding "trial
sessions before they're a member" introduces a fourth kind of
attendance attribution and is out of scope for v1.

### 4. Convert flow — auto-fill + plan picker, single transaction

Convert is the most important action in this feature. It must be
**atomic** and **frictionless**.

Auto-fill:
- `Member.first_name = lead.first_name`
- `Member.last_name = lead.last_name`
- `Member.phone = lead.phone`
- `Member.email = lead.email`
- `Member.notes` ← optional copy of `lead.notes` (UI checkbox; default
  on)
- `Member.join_date = today` in the tenant's timezone

User picks:
- **Plan** (dropdown of active membership plans) — required
- **Subscription start date** — defaults to today, can backdate up to
  30 days (the lead's trial may have started a week ago)
- **Payment method** — same field as the existing subscription create

Backend writes, in a single Postgres transaction:
1. INSERT `members` row (matching the existing `MemberService.create`
   semantics — phone collision still 409s)
2. INSERT `subscriptions` row (matching `SubscriptionService.create`)
3. UPDATE `leads` SET status='converted', converted_member_id=<new>,
   updated_at=now()
4. INSERT `lead_activities` row of type `status_change`,
   note=`"Converted to member <member_id>, plan <plan_id>"`

If any step fails (e.g. phone collision because a member with this
phone already exists), the entire transaction rolls back. Lead stays
in its previous state. The error humanizer surfaces "מנוי עם מספר
טלפון זה כבר קיים — האם זה אותו אדם?" with a link to the existing
member.

**Why single endpoint, not two?** A two-call flow ("create member,
then mark lead converted") leaves a window where the lead points to a
member that doesn't exist (or where a member exists with no lead
linkage). Single endpoint, single transaction, no race.

### 5. Activity types — call / email / note / meeting / status_change

Five types. The first four are user-logged; `status_change` is
**always** auto-generated by the service on a transition (never
accepted from the client).

Why these five:
- `call` — most common touchpoint at an Israeli gym; phone-first
  culture
- `email` — async follow-ups, especially for younger leads
- `meeting` — covers in-person trials, walk-in chats, scheduled
  consultations. We renamed `trial_booked` / `trial_completed` (from
  the original spec) to a single `meeting` type to avoid pretending
  trials have a separate state machine they don't
- `note` — catch-all for anything that isn't a contact attempt
  ("said she'd think about it and call back")
- `status_change` — system-generated audit row on every status flip,
  including conversion and reopen. Carries the old + new status in
  the `note` field as JSON-ish text (`"new → contacted"`)

Activity rows are **immutable**: no edit, no delete. The lead's
timeline is the audit trail. If a sales rep logs a wrong note, they
add a correction note ("nvm, that was a different lead").

### 6. Lost reason — free text with autocomplete

Lost reasons drive a real reporting question — "why are we losing
people?" — but rigid enums force gyms to fit their reasons into our
buckets. Compromise: free text, with autocomplete from the tenant's
own recent reasons.

Implementation:
- `leads.lost_reason TEXT` (nullable). Set when status moves to
  `lost`; stays put when reopened (we keep the historical reason in
  the activity row, but the column gets cleared on reopen).
- Autocomplete endpoint: `GET /api/v1/leads/lost-reasons` →
  `[{ reason, count }, ...]`. Returns the tenant's most-used lost
  reasons across the last 90 days, top 10 by count, case-insensitive
  collapse.
- Frontend: when dragging to `lost`, dialog has a text input wired to
  this endpoint with type-ahead. User can pick a suggestion or type
  something brand new.

The dashboard later will surface the top reasons as a small chart.

### 7. Feature flag — OFF by default, gated at service layer

Same mechanism as Schedule. `tenants.features_enabled.leads` boolean,
defaults to `false` for new tenants, super_admin toggles via the
existing `PATCH /tenants/:id/features` endpoint.

Service-layer guard at the top of every `LeadService` method:
```python
if not is_feature_enabled(tenant, "leads"):
    raise FeatureDisabledError("leads")
```

`FeatureDisabledError` already exists from the Schedule PR; reuse it.
Returns HTTP 403 with detail `FEATURE_DISABLED`. Frontend
`humanizeLeadError` translates to "תכונת לידים אינה זמינה לחדר כושר
זה. פנו למנהל המערכת".

Existing tenants get the flag backfilled to `false` in the migration
that introduces the table — silent no-op until the owner enables it.
(Coaches got `{coaches: true}` because it was already shipped;
Schedule got `{schedule: false}`. Leads gets `{leads: false}` — same
posture as Schedule.)

---

## State machine

```
                     ┌───────────────┐
       reopen ───────│     lost      │←───────┐
            │        └───────────────┘        │
            ▼                                 │
   ┌─────────┐   ┌───────────┐   ┌──────┐   │
   │   new   │──▶│ contacted │──▶│ trial │──▶│
   └─────────┘   └───────────┘   └──────┘   │
        │              │                │   │
        │              │                ▼   ▼
        │              │       ┌─────────────┐
        └──────────────┴──────▶│  converted  │
                               └─────────────┘
                                       (terminal)
```

**Allowed transitions** (enforced in `LeadService.set_status`):

| From | To | Notes |
|---|---|---|
| new | contacted, trial, converted, lost | first contact can skip stages — sometimes a walk-in converts on the spot |
| contacted | trial, converted, lost | |
| trial | converted, lost, contacted | "back to contacted" lets the rep say "trial didn't happen, still working on it" |
| converted | — | terminal. cannot reopen. (The created Member is the source of truth; if the gym needs to "un-convert", they cancel the Member.) |
| lost | contacted | reopen path. Resets `lost_reason` to NULL but keeps the historical activity row. |

Drag-to-converted is **not** allowed via the simple status PATCH — it
must go through the convert endpoint (which takes a plan + writes
member + sub + status change atomically). The Kanban UI omits
`converted` as a drop target; instead the card has an explicit
`המר למנוי` button.

---

## Data model

### Migration `0013_create_leads_and_lead_activities`

Adds two tables and the `leads: false` backfill on
`tenants.features_enabled`.

### `leads` table

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` |
| tenant_id | uuid | NOT NULL, FK → `tenants.id` ON DELETE CASCADE |
| first_name | text | NOT NULL |
| last_name | text | NOT NULL |
| email | text | nullable |
| phone | text | NOT NULL |
| source | text | NOT NULL, CHECK in (`walk_in`, `website`, `referral`, `social_media`, `ad`, `other`), default `'other'` |
| status | text | NOT NULL, CHECK in (`new`, `contacted`, `trial`, `converted`, `lost`), default `'new'` |
| assigned_to | uuid | nullable, FK → `users.id` ON DELETE SET NULL |
| notes | text | nullable |
| lost_reason | text | nullable; only meaningful when `status = 'lost'` |
| converted_member_id | uuid | nullable, FK → `members.id` ON DELETE SET NULL; set only when `status = 'converted'` |
| custom_fields | jsonb | NOT NULL, default `'{}'` (reserved for future per-tenant fields, no UI in v1) |
| created_at | timestamptz | NOT NULL, default `now()` |
| updated_at | timestamptz | NOT NULL, default `now()`, auto-update trigger |

**Indexes:**
- `idx_leads_tenant_status` on `(tenant_id, status)` — Kanban
  bucketing, dashboard "leads in pipeline" widget
- `idx_leads_tenant_assigned` on `(tenant_id, assigned_to)` —
  per-rep lookups
- `idx_leads_tenant_created` on `(tenant_id, created_at DESC)` —
  default list ordering
- No UNIQUE on phone — leads can repeat (someone walks in twice
  before signing up). The convert flow's phone collision check is
  against `members`, not `leads`.

**CHECK constraints:**
- `chk_leads_converted_consistency` — when `status='converted'`,
  `converted_member_id IS NOT NULL`. (No reverse — a lead with a
  cleared member id but converted status is impossible to write
  through the API anyway.)
- `chk_leads_lost_reason_consistency` — when `status='lost'`,
  `lost_reason IS NOT NULL` is **not** required (some leads are
  closed without a reason — UI just nudges, doesn't require).

### `lead_activities` table

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| tenant_id | uuid | NOT NULL, FK → `tenants.id` ON DELETE CASCADE — denormalized for fast tenant scoping in queries |
| lead_id | uuid | NOT NULL, FK → `leads.id` ON DELETE CASCADE |
| type | text | NOT NULL, CHECK in (`call`, `email`, `note`, `meeting`, `status_change`) |
| note | text | NOT NULL — free text body of the activity. For `status_change` rows, contains the transition (e.g. `"new → contacted"` or `"trial → lost; reason: יקר מדי"`) |
| created_by | uuid | nullable, FK → `users.id` ON DELETE SET NULL — null if the row was generated by a system task (none planned today, but reserved) |
| created_at | timestamptz | NOT NULL, default `now()` |

**Indexes:**
- `idx_lead_activities_lead_created` on `(lead_id, created_at DESC)` —
  the timeline query
- `idx_lead_activities_tenant_created` on `(tenant_id, created_at DESC)`
  — "what did the team do today?" reporting widget (future)

**No UPDATE / DELETE in the API.** Activities are append-only. The
repo intentionally has no `update` method. (Hard-delete on lead delete
is fine via the cascade FK — orphaned activities serve no purpose.)

### `tenants.features_enabled` — extended

The existing JSONB column gains a `leads` key:

```json
{
  "coaches": true,
  "schedule": false,
  "leads": false
}
```

Backfilled to `false` for all existing tenants in the same migration.
The frontend's `GATED_FEATURES` Set in `permissions.ts` adds `"leads"`.

---

## Domain (Layer 3)

### `domain/entities/lead.py`

```python
class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL = "trial"
    CONVERTED = "converted"
    LOST = "lost"

class LeadSource(StrEnum):
    WALK_IN = "walk_in"
    WEBSITE = "website"
    REFERRAL = "referral"
    SOCIAL_MEDIA = "social_media"
    AD = "ad"
    OTHER = "other"

class Lead(BaseEntity):
    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str
    source: LeadSource
    status: LeadStatus
    assigned_to: UUID | None
    notes: str | None
    lost_reason: str | None
    converted_member_id: UUID | None
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def can_transition_to(self, new_status: LeadStatus) -> bool: ...
    def is_open(self) -> bool:
        return self.status not in {LeadStatus.CONVERTED, LeadStatus.LOST}
    def full_name(self) -> str: ...
```

`can_transition_to` encodes the matrix from the state-machine section
above. It returns `False` for converted-as-source (terminal) and for
direct drag-to-converted (forces use of the convert endpoint). The
service raises `InvalidLeadStatusTransitionError` → 409 when violated.

### `domain/entities/lead_activity.py`

```python
class LeadActivityType(StrEnum):
    CALL = "call"
    EMAIL = "email"
    NOTE = "note"
    MEETING = "meeting"
    STATUS_CHANGE = "status_change"

class LeadActivity(BaseEntity):
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    type: LeadActivityType
    note: str
    created_by: UUID | None
    created_at: datetime
```

No methods — this entity is data only. All business logic lives in
`LeadService`.

### Exceptions (added to `domain/exceptions.py`)

- `LeadNotFoundError` → 404
- `InvalidLeadStatusTransitionError` → 409
- `LeadAlreadyConvertedError` → 409 (convert endpoint called on a
  lead in `converted` state)
- (Reused) `FeatureDisabledError` → 403

`MemberAlreadyExistsError` propagates up unchanged from the convert
endpoint when there's a phone collision against existing members.

---

## Service (Layer 2)

### `services/lead_service.py`

```python
class LeadService:
    async def create(self, caller: User, data: LeadCreate) -> Lead: ...

    async def get(self, caller: User, lead_id: UUID) -> Lead: ...

    async def list_for_tenant(
        self, caller: User, *,
        status: list[LeadStatus] | None = None,
        source: list[LeadSource] | None = None,
        assigned_to: UUID | None = None,
        search: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Lead]: ...

    async def update(self, caller: User, lead_id: UUID, data: LeadUpdate) -> Lead: ...

    async def set_status(
        self, caller: User, lead_id: UUID, *,
        new_status: LeadStatus,
        lost_reason: str | None = None,
    ) -> Lead: ...

    async def assign(self, caller: User, lead_id: UUID, user_id: UUID | None) -> Lead: ...

    async def convert(
        self, caller: User, lead_id: UUID, *,
        plan_id: UUID,
        start_date: date | None = None,
        payment_method: PaymentMethod,
        copy_notes_to_member: bool = True,
    ) -> ConvertResult: ...   # returns {lead, member, subscription}

    async def list_activities(
        self, caller: User, lead_id: UUID, *,
        limit: int = 100, offset: int = 0,
    ) -> list[LeadActivity]: ...

    async def add_activity(
        self, caller: User, lead_id: UUID, *,
        type: LeadActivityType, note: str,
    ) -> LeadActivity: ...

    async def list_lost_reasons(self, caller: User, *, days: int = 90, limit: int = 10) -> list[LostReasonRow]: ...
```

### Business rules (enforced in service)

- **Feature flag gate** — every method short-circuits with
  `FeatureDisabledError` when `tenant.features_enabled.leads` is
  false.
- **Tenant scoping** — every read/write asserts
  `lead.tenant_id == caller.tenant_id`. Cross-tenant lookups return
  404 (consistent with members/coaches; we don't leak existence).
- **Permission baseline** — owner: full; sales: full;
  super_admin: full (platform); staff: read-only — `create`,
  `update`, `set_status`, `convert`, `add_activity`, `assign` all
  raise `InsufficientPermissionsError` for staff. coach: no access at
  all (gated at `RequireFeature` + service layer).
- **State machine** — `set_status` calls `lead.can_transition_to`;
  raises `InvalidLeadStatusTransitionError` on invalid moves. Also
  emits a `status_change` activity row in the same transaction.
- **No drag-to-converted via `set_status`** — converting is a
  separate endpoint. `set_status` rejects `new_status=converted`
  with a clear 409.
- **`add_activity` cannot create `status_change`** — that type is
  reserved for the system. Service rejects with 422 if the client
  tries to send `type=status_change`.
- **Convert is one transaction** — see §"Decisions" §4. Service uses
  `async with session.begin():` to wrap all four writes. On
  `MemberAlreadyExistsError` from `MemberService.create`, the txn
  rolls back and the error propagates. The frontend's
  `humanizeLeadError` then catches it specifically to surface the
  collision message.
- **Lost reason persistence** — when `set_status(lost, lost_reason=X)`,
  set the column and include the reason in the activity note. When
  reopening from lost, clear the column but keep the historical
  activity row.
- **`assigned_to` validation** — must be a `users` row in the same
  tenant. Cross-tenant assignment raises 404 (treats foreign user as
  not-found, same posture as members).
- **No bulk operations in v1** — single-lead endpoints only. Bulk
  reassignment ("transfer 30 leads from departing rep to new rep") is
  a future enhancement once the volume justifies it.

---

## Adapter (Layer 4)

### Repositories

`adapters/storage/postgres/lead/repositories.py`:

- `create(tenant_id, data) -> Lead`
- `find_by_id(lead_id) -> Lead | None`
- `list_for_tenant(tenant_id, *, status, source, assigned_to, search, limit, offset) -> list[Lead]`
- `count_by_status(tenant_id) -> dict[LeadStatus, int]` — for the
  Kanban header counts and dashboard widget
- `update(lead_id, **fields) -> Lead`
- `top_lost_reasons(tenant_id, *, since, limit) -> list[LostReasonRow]`
  — `SELECT lower(lost_reason) AS reason, COUNT(*) FROM leads WHERE tenant_id=:t AND status='lost' AND lost_reason IS NOT NULL AND updated_at >= :since GROUP BY lower(lost_reason) ORDER BY 2 DESC LIMIT :limit`

`adapters/storage/postgres/lead_activity/repositories.py`:

- `create(tenant_id, data) -> LeadActivity`
- `list_for_lead(lead_id, *, limit, offset) -> list[LeadActivity]`

The convert flow uses the **session** directly (it spans 3 repos +
one update) — `LeadService.convert` opens the transaction and calls
`MemberService` / `SubscriptionService` from inside it, threading the
session.

---

## API (Layer 1)

### Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/leads` | sales+ / staff- | Create lead |
| GET | `/api/v1/leads` | Bearer (tenant-scoped) | List with filters: `status`, `source`, `assigned_to`, `search`, `limit`, `offset` |
| GET | `/api/v1/leads/{id}` | Bearer (tenant-scoped) | Get one lead |
| PATCH | `/api/v1/leads/{id}` | sales+ | Update (name, email, phone, source, notes, custom_fields) |
| POST | `/api/v1/leads/{id}/status` | sales+ | Set status. Body: `{new_status, lost_reason?}`. Rejects `new_status=converted`. |
| POST | `/api/v1/leads/{id}/assign` | sales+ | Body: `{user_id}` or `{user_id: null}` to unassign |
| POST | `/api/v1/leads/{id}/convert` | sales+ | Body: `{plan_id, start_date?, payment_method, copy_notes_to_member?}` → returns `{lead, member, subscription}` |
| GET | `/api/v1/leads/{id}/activities` | Bearer (tenant-scoped) | Timeline (paginated) |
| POST | `/api/v1/leads/{id}/activities` | sales+ | Body: `{type, note}` — `type` cannot be `status_change` |
| GET | `/api/v1/leads/lost-reasons` | sales+ | Top lost reasons in the last 90 days for autocomplete |
| GET | `/api/v1/leads/stats` | Bearer (tenant-scoped) | `{ counts: {new, contacted, trial, converted, lost}, conversion_rate_30d }` — for dashboard |

`sales+` here means **owner / sales / super_admin**. `staff-` means
staff is **excluded** from writes but can read (`GET` only).

All endpoints pass through the existing `is_feature_enabled` guard at
the service layer; calling them on a tenant with leads OFF returns
403 `FEATURE_DISABLED`.

### Schemas (sketch)

**`CreateLeadRequest`**
```json
{
  "first_name": "Yael",
  "last_name": "Cohen",
  "phone": "+972-50-123-4567",
  "email": null,
  "source": "walk_in",
  "assigned_to": "user-uuid-or-null",
  "notes": "Came in asking about boxing. Had a friend who used to come."
}
```

Required: `first_name`, `last_name`, `phone`. Server defaults: `source='other'`, `status='new'`.

**`UpdateLeadRequest`** — every field optional. Status is NOT
mutable here — use `/status`.

**`SetStatusRequest`**
```json
{ "new_status": "lost", "lost_reason": "יקר מדי" }
```

`lost_reason` is ignored unless `new_status='lost'`. Sending
`new_status='converted'` is rejected with 409.

**`ConvertLeadRequest`**
```json
{
  "plan_id": "...",
  "start_date": "2026-04-27",
  "payment_method": "cash",
  "copy_notes_to_member": true
}
```

**`ConvertLeadResponse`**
```json
{
  "lead": { ... },
  "member": { ... },
  "subscription": { ... }
}
```

**`AddActivityRequest`**
```json
{ "type": "call", "note": "Left voicemail. Will try again Tuesday." }
```

**`LeadResponse`** — full entity.

**`LeadActivityResponse`** — full activity entity.

---

## Frontend

### Feature folder

```
features/leads/
├── api.ts                   # ~10 endpoint wrappers
├── hooks.ts                 # TanStack Query hooks
├── types.ts                 # re-exports from api-types
├── LeadsPage.tsx            # /leads — Kanban board
├── KanbanBoard.tsx          # 5 columns, drag-and-drop
├── LeadCard.tsx             # the draggable card
├── LeadDetailPage.tsx       # /leads/:id — timeline + actions
├── LeadDetailHeader.tsx     # name, status badge, assigned-to, actions
├── ActivityTimeline.tsx     # ordered list of activity rows + inline forms
├── ActivityForm.tsx         # "+ שיחה / מייל / פגישה / הערה" picker
├── ConvertLeadDialog.tsx    # plan picker + start date + payment method
├── LostReasonDialog.tsx     # text input with autocomplete
├── LeadForm.tsx             # shared create/edit
└── *.test.tsx
```

### Layout sketch — `/leads` (Kanban)

```
┌─ PageHeader: "לידים" ─────────────────────────────────────────────┐
│  [+ ליד חדש]  [חיפוש: ...]   [מקור: כל המקורות ▼]  [רפרש]            │
└────────────────────────────────────────────────────────────────────┘

┌──── חדש (5) ──┬─ נוצר קשר (12) ─┬── ניסיון (3) ──┬─ הומר (24) ─┬─ אבוד (8) ─┐
│               │                 │                │             │            │
│  Yael Cohen   │  David Levy     │ Maya Bar       │ Noa Adler   │ Tomer Bar  │
│  walk_in      │  referral       │ walk_in        │ website     │  ad         │
│  preview note │  call yesterday │  trial Tue     │ converted   │ "יקר מדי"   │
│  3 days ago   │  2 days ago     │  yesterday     │  5 days ago │  1 wk ago   │
│  ─────────    │  ────────       │  ──────        │             │             │
│  ...          │  ...            │                │             │             │
│               │                 │                │             │             │
└───────────────┴─────────────────┴────────────────┴─────────────┴─────────────┘
```

- Cards drag between columns. The `converted` column is **drop-disabled**;
  cards have an explicit `המר למנוי` button on hover instead.
- Drop on `lost` opens `LostReasonDialog` before committing the change.
- Click a card → navigate to `/leads/:id`.
- Top counts come from `GET /leads/stats` and update on every move.

### Layout sketch — `/leads/:id` (detail)

```
┌─ ← חזרה ──────────────────────────────────────────────────────┐
│  Yael Cohen   [סטטוס: נוצר קשר]  [שייך ל: Roni ▼]               │
│  +972-50-123-4567   yael@example.com                            │
│  מקור: walk_in   נוצר: לפני 5 ימים                                │
│                                                                 │
│  [✏️ עריכה]  [⏯ המר למנוי]  [⨯ אבוד]                            │
└─────────────────────────────────────────────────────────────────┘

┌─ ציר זמן ─────────────────────────────────────────────────────┐
│  + שיחה   + מייל   + פגישה   + הערה                            │
│  ────────────────────────────────────────────────────────────   │
│  Roni · לפני 2 שעות · שיחה                                       │
│   "Left voicemail. Will try again Tuesday."                      │
│  ────────────────────────────────────────────────────────────   │
│  System · אתמול · status_change                                  │
│   "new → contacted"                                              │
│  ────────────────────────────────────────────────────────────   │
│  Roni · לפני יומיים · הערה                                       │
│   "Walked in. Asked about boxing."                               │
└─────────────────────────────────────────────────────────────────┘
```

### Convert flow UI

`ConvertLeadDialog`:
- Shows the lead's auto-filled fields (read-only preview)
- **Plan** combobox — populated from `usePlans({status: "active"})`
- **Start date** — date picker, default today, allow up to 30 days
  back
- **Payment method** — same select used in the existing subscription
  form
- **"העתק הערות מהליד"** checkbox, default on
- Submit → `useConvertLead`. On success, navigate to
  `/members/<new_member_id>`. On 409 phone collision, show the
  Hebrew message inline with a link to the existing member.

### Routes + permissions

```tsx
<Route element={<RequireFeature feature="leads" />}>
  <Route path="/leads" element={<LeadsPage />} />
  <Route path="/leads/:id" element={<LeadDetailPage />} />
</Route>
```

`RequireFeature feature="leads"` checks both:
1. `canAccess(user, "leads")` — role baseline (owner / sales /
   super_admin / staff-read)
2. `tenantFeatures.leads === true` — gated feature flag

Sidebar adds a `NAV_ITEMS` entry: `{ feature: "leads", to: "/leads",
label: "לידים", icon: "users-plus" }`.

| Role | Leads feature |
|---|---|
| owner | Full CRUD + convert |
| sales | Full CRUD + convert |
| super_admin | Full (platform — rare to actually use, but allowed) |
| staff | Read-only (sees Kanban + detail; no edit buttons) |
| coach | No access — `canAccess` returns false |

### Error humanizer

`humanizeLeadError` in `lib/api-errors.ts`:

- 403 `FEATURE_DISABLED` → "תכונת לידים אינה זמינה לחדר כושר זה. פנו
  למנהל המערכת"
- 403 → "אין לכם הרשאה לפעולה זו"
- 404 → "הליד לא נמצא"
- 409 `LEAD_ALREADY_CONVERTED` → "הליד כבר הומר למנוי"
- 409 `INVALID_TRANSITION` → "לא ניתן לבצע מעבר זה במצב הנוכחי"
- 409 `MEMBER_ALREADY_EXISTS` (from convert) → "מנוי עם מספר טלפון
  זה כבר קיים. בדקו אם זה אותו אדם." (with link to existing member if
  the API returns the colliding id — TBD during implementation)
- 422 → "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"

---

## Observability

Structlog events:

| Event | Fields | When |
|---|---|---|
| `lead.created` | tenant_id, lead_id, source, assigned_to | Lead create |
| `lead.status_changed` | tenant_id, lead_id, from, to, by, lost_reason? | Status PATCH |
| `lead.activity_added` | tenant_id, lead_id, activity_id, type | New activity |
| `lead.assigned` | tenant_id, lead_id, from, to | assign endpoint |
| `lead.converted` | tenant_id, lead_id, member_id, subscription_id, plan_id | Successful convert (after txn commit) |
| `lead.convert_failed` | tenant_id, lead_id, error_code | Convert txn rolled back (e.g. phone collision) |
| `lead.feature_blocked` | tenant_id, endpoint | Service-layer FeatureDisabledError |

Dashboard queries (added next phase):
- `count(*) WHERE tenant_id=:t AND status IN ('new','contacted','trial')` — "leads in pipeline" widget
- `count(*) WHERE status='converted' AND updated_at >= now() - 30d / count(*) WHERE created_at >= now() - 30d` — "30-day conversion rate"
- `top_lost_reasons` already implemented — surfaces as a small chart later

---

## Tests

### Backend

| Type | File | Coverage |
|---|---|---|
| Unit | `test_lead_entity.py` | `can_transition_to` matrix; `is_open`; `full_name`; required fields |
| Unit | `test_lead_activity_entity.py` | type enum; required fields |
| Unit | `test_lead_service.py` | mocked repo — feature-flag gate; tenant scoping; permission gates per role; state machine; status_change auto-row; convert reject when lead in `converted`; activity-type rejects `status_change` from clients |
| Integration | `test_lead_repo.py` | CRUD; cross-tenant isolation; status filter; search; `count_by_status`; `top_lost_reasons` aggregation |
| Integration | `test_lead_activity_repo.py` | append; tenant scoping; ordering by created_at desc |
| Integration | `test_lead_convert_txn.py` | convert flow happy path; phone collision rolls back lead+member+sub+activity; missing plan rolls back; cross-tenant plan rolls back |
| E2E | `test_leads.py` | full HTTP — create, list (with filters), update, set_status, assign, add_activity, list_activities, lost_reasons, stats; 403 for cross-tenant; 404 for missing |
| E2E | `test_lead_convert.py` | end-to-end convert: lead→member→subscription, then `/members/<id>` returns the auto-filled member; activity timeline shows the convert status_change |
| E2E | `test_leads_feature_flag.py` | every endpoint returns 403 `FEATURE_DISABLED` when flag off; super_admin toggles, then endpoints work |
| E2E | `test_cross_tenant_isolation.py` (additions) | ~10 probes for leads + activities + convert + assign |

Target: **~40 new backend tests**.

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | Each endpoint wrapper sends right URL + body |
| `KanbanBoard.test.tsx` | 5 columns; cards bucketed by status; drop dispatches mutation; drop-on-converted disabled |
| `LeadCard.test.tsx` | name + source + days-in-stage + click navigates |
| `ActivityTimeline.test.tsx` | timeline order; "+ שיחה" inline form; submit appends |
| `ActivityForm.test.tsx` | type picker; cannot pick status_change |
| `ConvertLeadDialog.test.tsx` | plan select; date picker; payment method; submit shape; 409 phone collision shows link |
| `LostReasonDialog.test.tsx` | autocomplete fetches; can pick suggestion; can type new |
| `LeadForm.test.tsx` | required fields; submit shape (create vs edit) |
| `LeadsPage.test.tsx` | feature-flag-off shows nothing (RequireFeature); search debounce; column counts come from /stats |
| `LeadDetailPage.test.tsx` | header + timeline + actions render; convert button visible only for owner/sales |
| `permissions.test.ts` (additions) | sales/owner/staff/coach matrix for `"leads"` |
| `lib/api-errors.test.ts` (additions) | `humanizeLeadError` for each status / code branch |

Target: **~25 new frontend tests**.

### Load test

`loadtests/test_leads_load.py`:

- `KanbanBrowser` VU — `GET /leads/stats` + `GET /leads?status=new,contacted,trial,lost&limit=50` every 15s.
- `SalesRep` VU — random walk: create → add 1–3 activities → set_status → eventually convert OR lost. Mimics real daily flow.
- Targets:
  - 99p `/leads/stats` < 80ms at 10 VU (uses the
    `idx_leads_tenant_status` index — should be a count-by-group hit)
  - 99p `/leads/{id}/convert` < 250ms at 5 VU (the txn does 4 writes
    + plan lookup; 250ms is generous, watch for regressions)

---

## V1 → future migration path

Nothing in v1 boxes in v2.

- **Custom pipeline stages** — when Phase 4 dynamic config lands,
  introduce `tenant_pipeline_stages` table (per tenant). The
  hardcoded `LeadStatus` enum becomes a CHECK constraint that
  references this table OR (more likely) becomes a `text` column with
  service-layer validation against tenant config. Existing tenants
  get a default pipeline of the v1 5 stages; nothing breaks.
- **Assigned-only visibility for sales** — a per-tenant toggle in
  `tenants.feature_configs` (`leads.sales_sees_assigned_only=true`).
  Service-layer reads it and adds `WHERE assigned_to = caller.id` to
  `list_for_tenant` for sales callers.
- **Dynamic activity types** — same story. v1's enum becomes a
  per-tenant list when configurability lands. Existing rows are
  preserved.
- **Bulk reassignment** — `POST /leads/bulk-reassign` body
  `{from_user_id, to_user_id, status?}` — applies in one txn, logs an
  `assigned` activity per affected lead. Useful when a sales rep
  leaves the gym.
- **Email integration** — outbound: `add_activity(type=email)` could
  optionally trigger a real email send via SES. Inbound: parse
  `Reply-To: leads-<lead_id>@<tenant>.dopacrm.com` and append the
  reply as a `note` activity. Big surface — defer.
- **Lead capture forms** — public landing page form posts to a
  rate-limited `POST /api/v1/leads/public` endpoint with a
  per-tenant captcha and source=`website`. Out of scope for v1.

---

## Open questions (to revisit during implementation)

1. **Phone collision pre-check on lead create?** Today we don't —
   leads can repeat. Should the create endpoint at least *warn* in
   the response if a member with the same phone already exists ("did
   you mean to look up the existing member instead of creating a
   lead?"). Leaning yes — UI hint, not a hard 409.
2. **Show member's lead history on the member detail page?** When a
   lead converts, its `id` is recorded on the member as
   `originated_from_lead_id` (extra column on `members`?). Useful
   for "where did our converted members come from?" reports. Adds
   one column; decide during implementation.
3. **Assignment notifications.** When `assigned_to` changes, do we
   email the new owner? v1: no — sales rep checks the Kanban. Email
   notifications are a notification-system question, deferred.
4. **Lost-reason normalization.** Free text means "יקר", "יקר מדי",
   "יותר מדי כסף" all end up as separate rows. The autocomplete
   helps. Should the dashboard chart group similar reasons (some
   manual mapping in tenant config)? Out of scope for v1; revisit
   when the chart lands.
5. **Activity edit/delete?** v1: no — append-only. Some users will
   ask for a "soft delete" (mark as wrong, hide). Defer until we
   have a real complaint; add an `activity.is_hidden` column then.
6. **Trial scheduling.** Tomorrow we add a "+ קבע ניסיון" button that
   takes a `class_session_id` and writes a `meeting` activity with
   structured metadata pointing at the session. v1 keeps it free-text
   to avoid binding the schemas before we know the UX.

---

## Migration plan

Single combined PR — backend + frontend + flag wiring. Estimate:
**2 days** (smaller than Schedule because there's no calendar grid,
no beat job, no DST math; bigger than Coaches because of the
Kanban + drag/drop + convert txn).

**Backend:**

1. Migration `0013`: `leads` + `lead_activities` tables, indexes,
   CHECK constraints, `tenants.features_enabled.leads = false`
   backfill.
2. Domain entities (`lead`, `lead_activity`) + exceptions + unit
   tests.
3. Repos for both tables.
4. `LeadService` — CRUD, state machine, activities,
   `top_lost_reasons`, stats.
5. `LeadService.convert` — atomic txn calling `MemberService.create`
   + `SubscriptionService.create` from inside.
6. Routes + schemas — 10 endpoints listed above.
7. E2E tests including feature-flag isolation + cross-tenant probes.

**Frontend:**

1. Feature folder with pages/components.
2. `Feature` union: `+ "leads"`. `GATED_FEATURES`: add `"leads"`.
   `BASELINE`: owner / sales get full; staff gets read-only;
   super_admin platform; coach: no access.
3. Sidebar entry + route guards.
4. `humanizeLeadError`.
5. Tenant detail page already shows the Features section — adding
   `"leads"` to `GATED_FEATURES` makes it appear automatically (no
   per-feature UI work).
6. Tests.

**Docs / spec:**

1. `docs/spec.md` §3.8 — replace with a one-paragraph pointer to
   this doc; tighten the activity-types list to match v1; note the
   feature flag.
2. `docs/crm_logic.md` — add Leads to the permission-layering
   section + a one-paragraph note on the convert transaction.
3. `docs/features/leads.md` — this doc, authoritative.
4. `docs/features/feature-flags.md` — add a row to the registry
   table for `leads`.

---

## Related docs

- [`spec.md`](../spec.md) §3.8 — product-level overview of leads
- [`crm_logic.md`](../crm_logic.md) — cross-feature rules (the
  convert txn touches Members + Subscriptions + Leads)
- [`feature-flags.md`](./feature-flags.md) — the gating mechanism
- [`members.md`](./members.md) — the entity convert creates
- [`subscriptions.md`](./subscriptions.md) — the side-effect convert
  also creates
- [`roles.md`](./roles.md) — when dynamic roles ship, lead
  permissions become per-tenant configurable
