# Feature: Subscriptions

> **Status:** Planned. Not yet implemented. Plan for review.
>
> **Order:** Build AFTER Members + Membership Plans (both shipped). BEFORE Payments (they FK into subscriptions).
>
> **What this is:** The link between a Member and a Plan. A Member + a Plan + a price snapshot + a lifecycle status. This is the entity that finally makes the CRM a CRM — revenue, churn, freezes, renewals, MRR all live here.

---

## Summary

A Subscription records that "Dana is on the Monthly Unlimited plan for 250 ILS, started March 1st, currently active". Plans are the **catalog** (what the gym sells); Subscriptions are the **assignments** (who bought what and when).

This is the feature that turns the dashboard placeholder "בקרוב" into real MRR numbers, that makes "expiring this week" work, that lets the Freeze button on a member actually pause their billing.

---

## Why not just put `plan_id + status + price` columns on `members`?

Same question we answered for Plans, same "obvious lazy design is wrong" pattern. Five reasons:

### 1. Members change plans over time

Dana starts on Monthly Unlimited in Jan, switches to 10-class pack in March, upgrades to Annual in October. If the plan reference lives on `members`, each switch overwrites history — you lose "what plan was Dana on in March?", you lose "how often do members downgrade?", you lose the churn funnel. Subscriptions is what gives you a temporal history of plan assignments.

### 2. Price is locked per-subscription, not per-plan

The owner raises "Gold Pass" from 250 to 300 ILS in May. Members who signed up in April at 250 should keep paying 250 until they cancel or switch plans. That requires the price to be snapshotted AT SUBSCRIPTION TIME, in a column on the Subscription row — not derived from the current plan price. You can't do that with a `members.plan_id` column alone.

### 3. Freezing pauses billing, not membership

A Member who's traveling for a month shouldn't churn — they freeze. But "freeze" is a property of the COMMERCIAL RELATIONSHIP, not the person. If `members.status = frozen`, you're overloading the person record with billing semantics. Subscriptions own the `frozen_at` / `frozen_until` columns; Member.status derives from (or mirrors) the current sub's state.

### 4. A cancelled Subscription is history, not a dead member

When Dana cancels in June, the Subscription becomes `cancelled` with `cancelled_at` set. The Member row stays — Dana is still a person who existed, her payment history still matters. If she rejoins in August, that's a NEW Subscription row, not a mutation of the old one. The gym can legitimately ask "how many churned members rejoined within 3 months?" — only possible with Subscriptions as separate rows.

### 5. The dashboard asks questions that need JOIN m ↔ s ↔ p

- "MRR from recurring subscriptions active right now" — `SUM(price_cents) WHERE status='active' AND plan.type='recurring'`
- "Expiring in the next 7 days" — `expires_at BETWEEN now AND now+7d`
- "Revenue per plan this month" — `JOIN subscriptions ON plan_id GROUP BY plan_id`
- "Churn rate — cancellations / active subs this month" — requires `cancelled_at` as a sortable column

These queries are obvious with a `subscriptions` table. They're impossible with denormalized columns on Member.

---

## Where this sits in Phase 2

```
  Phase 2 build order
  ────────────────────
  Members             shipped
  Classes             shipped
  Membership Plans    shipped
  Subscriptions       ← THIS DOC (next)
  Payments            ← needs Subscriptions
  Leads               ← independent, can ship anytime
```

Subscriptions depend on Members (subject of the subscription) and Plans (what they're subscribed to). Payments depend on Subscriptions (which subscription is this payment for?).

---

## The state machine

```
  (created)──► active ◄──────────────────┐
                │  ▲  ▲                  │
                │  │  └──(renew)─── expired   (soft-terminal — renewable)
                │  │                     ▲
                │  │                     │ (expiry job: expires_at < today)
                │  └──(unfreeze)──── frozen
                │                        ▲
                │                        │ (freeze)
                │                        │
                │  (change-plan)
                ├─────────────► replaced ── replaced_by_id ──► [new active sub]
                │
                └──(cancel)────► cancelled    (HARD-terminal)
```

### Transitions

| From | To | Trigger | Who | Side-effect on Member |
|---|---|---|---|---|
| — | `active` | Staff enrolls member in plan | staff+ | Member → `active` |
| `active` | `frozen` | Staff freezes (optional `frozen_until`) | staff+ | Member → `frozen` |
| `frozen` | `active` | Staff unfreezes manually | staff+ | Member → `active` |
| `frozen` | `active` | Daily job: `frozen_until <= today` | system | Member → `active` |
| `active` | `expired` | Daily job: `expires_at < today` | system | Member → `expired` |
| `active` / `expired` | `active` | **Renew** — staff records payment, `expires_at` pushed forward | staff+ | Member → `active` |
| `active` / `frozen` | `replaced` | **Change plan** — creates new sub, links via `replaced_by_id` | staff+ | Member status follows new sub |
| `active` / `frozen` / `expired` | `cancelled` | Member actively leaves | staff+ | Member → `cancelled` |

### Key rules

- **`cancelled` is HARD-terminal.** No transitions out. Undoing a cancel = create a new sub.
- **`expired` is SOFT-terminal.** It can transition back to `active` via **renew** (same row, same `started_at`, same price snapshot). This preserves the member's tenure date AND leaves a `days_late` breadcrumb in `subscription_events`.
- **`replaced` is terminal for the OLD sub only** — state transitions continue on the NEW sub it points to. Used exclusively for plan changes (upgrade/downgrade). Not in any reporting "churn" bucket.
- **Freezing extends `expires_at`.** Industry standard: paused time doesn't eat paid time. When a frozen sub is unfrozen after N days (auto or manual), `expires_at` is pushed forward by N days.
- **`active` → `active`** is blocked (surfaces accidental double-enrolls). To renew the same plan, use `/renew`; to switch plans, use `/change-plan`.

### Expiry: cash-paid vs card-auto

The expiry job is the *core* of the cash-payment workflow, not an edge case.

| Payment style | `expires_at` | Behavior |
|---|---|---|
| **Cash / prepaid cash** (owner sets renewal date each cycle) | Set to next payment due date | Expires if not renewed by staff |
| **Card auto-debit** (runs indefinitely) | `NULL` | Never expires on a date — only cancels on manual action |
| **Card prepaid N months** | Set to `started_at + N × 30d` | Expires like cash; staff renews next time |
| **One-time plan** (e.g., 14-day trial pass) | `started_at + plan.duration_days` | Expires; renewal = new sub |

When `expires_at < today AND status='active'`, the nightly job flips to `expired` (writes `expired_at = today`, logs an event). Staff's "about to expire this week" view queries `WHERE status='active' AND expires_at BETWEEN today AND today+7d`.

### Grace period

**Not a separate state.** The `expired` status IS the grace signal, and the "about-to-expire" dashboard is how staff contact members *before* they flip. No `past_due` / `grace` intermediate state — fewer transitions, fewer edge cases.

---

## Member.status vs Subscription.status — the sync problem

Both Members and Subscriptions have a `status` column with the same values: `active / frozen / cancelled / expired`. That is by design, not accident — the values are the same because the Member's status IS the status of their active commercial relationship with the gym.

Three possible designs:

### Option A: Derive Member.status from Subscription (no Member.status column)

- Clean: no drift possible
- Expensive: every member read joins against subscriptions
- Breaking: existing Member code + DB + tests all reference `members.status`

### Option B: Both store status; service keeps them synced *(pick this one)*

- Cheap reads: `SELECT status FROM members` still works
- Small invariant: every Subscription state change bumps Member.status in the same transaction
- The Member entity's state machine (already shipped) stays intact — we just give it a second writer besides the member endpoints

### Option C: Keep them independent

- Member.status tracks "is this person a customer" — set by the member CRUD endpoints
- Subscription.status tracks "is their payment plan active right now" — set by the sub endpoints
- Allows "cancelled sub but still an active member" states that confuse the dashboard and every report

**Decision: Option B.** SubscriptionService owns member.status updates on every sub transition. The Member entity's freeze/unfreeze/cancel methods still exist (they encapsulate the state machine) but are called FROM the sub service, not called directly from the member endpoints for commercial events.

**Consequence:** we will change `MemberService.freeze()` / `cancel()` to either:
- Deprecate them (commercial state changes go through Subscription endpoints), OR
- Have them delegate to SubscriptionService (they look up the active sub and freeze it, which cascades back)

Slight preference for deprecation + migration — simpler model. But this is callsite-churn that we'll scope with the implementation.

---

## User stories

1. **As staff**, I enroll a member: pick Member + active Plan, set `started_at` (default today; future dates allowed for "starts Monday"), optionally set `expires_at` (cash = "next payment due"; card-auto = leave null). System locks the current plan price.
2. **As staff**, I freeze a subscription (optional `frozen_until` for "back from trip June 15"). Frozen time will auto-extend `expires_at` on unfreeze.
3. **As staff**, I unfreeze a subscription manually (member came back early).
4. **As staff**, I **renew** a cash-paying member's subscription: hit `/renew`, `expires_at` pushes forward by the plan's billing cycle (or by an explicit date for "she paid 2 months upfront"). Works on both `active` subs (before expiry) and `expired` subs (rescue a lapsed member — her tenure date is preserved). System logs `days_late` so the owner can see "5 members renewed late this month".
5. **As staff**, I **change a member's plan** (Silver → Gold). System creates a new sub with a fresh price snapshot, marks the old one `replaced` (NOT cancelled — different for reports). Works on `active` and `frozen` subs.
6. **As staff**, I cancel a subscription when a member actively leaves. Optional reason dropdown (moved / too expensive / not using / injury / other + free text). HARD-terminal — rejoin = new sub.
7. **As the system (Celery beat)**, every night I auto-unfreeze any sub whose `frozen_until` has passed, auto-expire any sub whose `expires_at < today`, and log both events.
8. **As owner/staff**, on the member page I see their current subscription (plan, price, status, expires_at) and their full timeline via `subscription_events` (enrolled / frozen / renewed / late-by-N-days / cancelled).
9. **As the owner dashboard**, I read aggregates from subscriptions + events to compute MRR, expiring-this-week, churn rate, late-renewal rate.

**Explicitly NOT in this feature:**
- Recording payments against a subscription → Payments (Subscriptions v1 just tracks when `expires_at` moved; Payments connects the money).
- Automatic card charging → deferred (we don't process cards in v1).
- Prorated refunds → manual; owner/staff records a corrective payment when Payments lands.
- Scheduled plan changes ("switch me at next billing cycle, not now") → v2, add `scheduled_at` column later.
- Entitlement usage tracking ("3 classes/week — how many used?") → Attendance feature (Phase 3). New sub = fresh quota window.
- Multi-location / gym chains → deferred (see spec.md §5).

---

## API Endpoints

All tenant-scoped. The service rejects cross-tenant access with 404 (same pattern as Plans / Classes).

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/subscriptions` | staff+ | Enroll: `{member_id, plan_id, started_at?, expires_at?}` — `started_at` defaults to today, `expires_at` null = "runs until cancelled" (card-auto) |
| GET | `/api/v1/subscriptions` | Bearer | List (filterable: `?member_id=`, `?status=`, `?plan_id=`, `?expires_before=`, `?expires_within_days=`) |
| GET | `/api/v1/subscriptions/{id}` | Bearer | Get one |
| GET | `/api/v1/subscriptions/{id}/events` | Bearer | Timeline of events for this sub (enrolled/frozen/renewed/expired/cancelled) newest first |
| GET | `/api/v1/members/{id}/subscriptions` | Bearer | All subs for one member, newest first |
| GET | `/api/v1/members/{id}/subscriptions/current` | Bearer | Current live sub (status in active/frozen), or 404 |
| POST | `/api/v1/subscriptions/{id}/freeze` | staff+ | Body: `{frozen_until?: date}` |
| POST | `/api/v1/subscriptions/{id}/unfreeze` | staff+ | Manual unfreeze — auto-extends `expires_at` by frozen duration |
| POST | `/api/v1/subscriptions/{id}/renew` | staff+ | Body: `{new_expires_at?: date}`. Default: push `expires_at` forward by plan's billing_period days. Works on `active` AND `expired` subs |
| POST | `/api/v1/subscriptions/{id}/change-plan` | staff+ | Body: `{new_plan_id, effective_date?}`. Creates new sub with fresh price snapshot; marks old sub `replaced`, links them |
| POST | `/api/v1/subscriptions/{id}/cancel` | staff+ | Body: `{reason?: str}` (dropdown on frontend, free-text allowed). HARD-terminal |

### Why these specific endpoints

- **Why staff+ (not owner-only)?** Day-to-day enrollment, renewal, freeze, cancel are staff work. Owner-gated would block daily ops.
- **Why no `PATCH /subscriptions/{id}`?** Every mutation is a named state transition (freeze/unfreeze/renew/change-plan/cancel) — each has its own semantics, guard, and event log entry. Plain PATCH invites "let me edit the price" which breaks the lock-at-create-time rule. If an innocuous field like `notes` is added later, we add PATCH then.
- **Why no `DELETE`?** We never hard-delete. Cancel is the soft-delete; `replaced` is the plan-change equivalent.
- **Why renew works on expired subs too?** Gym reality: members forget and bring cash a day late. Letting staff rescue the existing sub (same `started_at`, same price lock) preserves tenure and makes the `days_late` data available to the owner. `cancelled` members who want to return = new sub (that was an active departure).

---

## Domain (Layer 3)

**`domain/entities/subscription.py`**

```python
class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    EXPIRED = "expired"      # SOFT-terminal — renew() can resurrect
    CANCELLED = "cancelled"  # HARD-terminal — rejoin = new sub
    REPLACED = "replaced"    # plan change — old sub; see replaced_by_id


class Subscription(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    plan_id: UUID

    status: SubscriptionStatus
    price_cents: int            # locked at create-time from plan.price_cents
    currency: str               # locked at create-time from plan.currency

    started_at: date
    expires_at: date | None     # NULL = card-auto "runs until cancelled"; set = cash/prepaid/one-time
    frozen_at: date | None
    frozen_until: date | None
    expired_at: date | None     # set when the sub flipped to expired (preserved across renew)
    cancelled_at: date | None
    cancellation_reason: str | None
    replaced_at: date | None
    replaced_by_id: UUID | None  # FK → subscriptions.id (new sub from plan change)

    created_at: datetime
    updated_at: datetime

    # ── State-machine methods (pure, no I/O) ──

    def can_freeze(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE

    def can_unfreeze(self) -> bool:
        return self.status == SubscriptionStatus.FROZEN

    def can_renew(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED)

    def can_change_plan(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FROZEN)

    def can_cancel(self) -> bool:
        return self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.FROZEN,
            SubscriptionStatus.EXPIRED,
        )

    def should_auto_unfreeze(self, today: date) -> bool:
        return (
            self.status == SubscriptionStatus.FROZEN
            and self.frozen_until is not None
            and self.frozen_until <= today
        )

    def should_auto_expire(self, today: date) -> bool:
        return (
            self.status == SubscriptionStatus.ACTIVE
            and self.expires_at is not None
            and self.expires_at < today
        )


class SubscriptionEventType(StrEnum):
    CREATED = "created"
    FROZEN = "frozen"
    UNFROZEN = "unfrozen"       # covers both manual and auto
    EXPIRED = "expired"
    RENEWED = "renewed"
    REPLACED = "replaced"        # old sub's side of a plan change
    CHANGED_PLAN = "changed_plan"  # new sub's side of a plan change
    CANCELLED = "cancelled"


class SubscriptionEvent(BaseModel):
    """Append-only timeline row. Written inside the same transaction as the state change."""
    id: UUID
    tenant_id: UUID
    subscription_id: UUID
    event_type: SubscriptionEventType
    event_data: dict[str, Any]  # e.g. {"days_late": 3, "frozen_until": "2026-06-15", "reason": "..."}
    occurred_at: datetime
    created_by: UUID | None     # None = system event (expiry job, auto-unfreeze)
```

**Exceptions** (added to `domain/exceptions.py`):
- `SubscriptionNotFoundError` → 404
- `InvalidSubscriptionStateTransitionError` → 409 (freeze a cancelled sub, renew a cancelled sub, etc.)
- `MemberAlreadyHasActiveSubscriptionError` → 409 (enrolling when one is already active/frozen)
- `SamePlanChangeError` → 409 (change-plan with the same plan_id as the current sub)
- `SubscriptionPlanMismatchError` → 422 (plan belongs to a different tenant — belt-and-suspenders vs the FK)

---

## Data Model

**`subscriptions` table** (migration `0008_create_subscriptions.py`)

```sql
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
  plan_id UUID NOT NULL REFERENCES membership_plans(id) ON DELETE RESTRICT,

  status TEXT NOT NULL CHECK (
    status IN ('active', 'frozen', 'expired', 'cancelled', 'replaced')
  ),
  price_cents INT NOT NULL CHECK (price_cents >= 0),
  currency TEXT NOT NULL,

  started_at DATE NOT NULL,
  expires_at DATE,
  frozen_at DATE,
  frozen_until DATE,
  expired_at DATE,                -- set on first flip to expired; preserved across renew
  cancelled_at DATE,
  cancellation_reason TEXT,
  replaced_at DATE,
  replaced_by_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Shape integrity: frozen subs must have frozen_at; cancelled must have cancelled_at; replaced must have replaced_at + replaced_by_id
  CHECK (
    (status <> 'frozen' AND frozen_at IS NULL AND frozen_until IS NULL)
    OR (status = 'frozen' AND frozen_at IS NOT NULL)
  ),
  CHECK (
    (status <> 'cancelled' AND cancelled_at IS NULL)
    OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
  ),
  CHECK (
    (status <> 'replaced' AND replaced_at IS NULL AND replaced_by_id IS NULL)
    OR (status = 'replaced' AND replaced_at IS NOT NULL AND replaced_by_id IS NOT NULL)
  ),

  -- frozen_until, if set, must be >= frozen_at
  CHECK (frozen_until IS NULL OR frozen_at IS NULL OR frozen_until >= frozen_at)
);

-- The "one LIVE sub per member" invariant, enforced at the DB level.
-- Partial unique index: a member can have multiple cancelled/expired/replaced subs
-- (history), but at most one in {active, frozen}.
CREATE UNIQUE INDEX idx_subscriptions_one_live_per_member
  ON subscriptions (member_id)
  WHERE status IN ('active', 'frozen');

-- Hot paths
CREATE INDEX idx_subscriptions_tenant_status ON subscriptions (tenant_id, status);
CREATE INDEX idx_subscriptions_member ON subscriptions (member_id, created_at DESC);
CREATE INDEX idx_subscriptions_expires ON subscriptions (tenant_id, expires_at)
  WHERE status = 'active' AND expires_at IS NOT NULL;
CREATE INDEX idx_subscriptions_frozen_until ON subscriptions (tenant_id, frozen_until)
  WHERE status = 'frozen' AND frozen_until IS NOT NULL;
```

**`subscription_events` table** — append-only timeline, one row per state transition.

```sql
CREATE TABLE subscription_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,

  event_type TEXT NOT NULL CHECK (event_type IN (
    'created', 'frozen', 'unfrozen', 'expired',
    'renewed', 'replaced', 'changed_plan', 'cancelled'
  )),
  event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- e.g. {"days_late": 3} on renew, {"frozen_until": "..."} on freeze,
  --      {"reason": "moved_away", "detail": "..."} on cancel

  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL
  -- NULL = system event (nightly expiry / auto-unfreeze jobs)
);

CREATE INDEX idx_sub_events_sub ON subscription_events (subscription_id, occurred_at DESC);
CREATE INDEX idx_sub_events_tenant_type ON subscription_events (tenant_id, event_type, occurred_at DESC);
```

**Design choices:**

- `ON DELETE RESTRICT` on `member_id` and `plan_id` — you can't delete a member or plan that has subs attached. Prevents orphaned history. Soft-delete (deactivate) is the only supported path for both.
- `ON DELETE CASCADE` on `tenant_id` — nuking a tenant nukes its subs too (consistent with members/plans).
- `replaced_by_id ON DELETE SET NULL` — defensive; the forward pointer nulls out if the new sub is ever removed. We don't hard-delete today, but the link staying hard would be wrong if we ever do.
- **Partial unique index** enforcing the "one live sub per member" rule *at the database*, not just the service layer. `replaced` and `expired` are EXCLUDED from the predicate — they're history, not live.
- Three partial indexes for the expiry/unfreeze/status-filter jobs — keeps the nightly jobs O(matching rows) not O(table).
- `currency` duplicated from plan — same lock-at-create-time reasoning as Plans.
- **`subscription_events` is append-only.** No UPDATE / DELETE. The row is written inside the same transaction as the state change on `subscriptions`, so either both land or both roll back — there's no "status changed but event missing" drift.
- `event_data` as JSONB lets us evolve event payloads without migrating the table every time (add `days_late`, `frozen_duration_days`, etc.). Reads that want a specific field use JSONB operators.

---

## Service (Layer 2)

`services/subscription_service.py`:

```python
class SubscriptionService:
    # Enrollment
    async def create(
        self, *, caller, member_id, plan_id,
        started_at: date | None = None,   # default today
        expires_at: date | None = None,   # None = card-auto, set = cash/prepaid/one-time
    ) -> Subscription: ...

    # Reads
    async def get(self, *, caller, sub_id) -> Subscription: ...

    async def list(
        self, *, caller,
        member_id: UUID | None = None,
        status: SubscriptionStatus | None = None,
        plan_id: UUID | None = None,
        expires_before: date | None = None,
        expires_within_days: int | None = None,  # "about to expire" dashboard
        limit: int = 100, offset: int = 0,
    ) -> list[Subscription]: ...

    async def list_for_member(
        self, *, caller, member_id: UUID
    ) -> list[Subscription]: ...

    async def get_current_for_member(
        self, *, caller, member_id: UUID
    ) -> Subscription | None: ...

    async def list_events(
        self, *, caller, sub_id: UUID
    ) -> list[SubscriptionEvent]: ...

    # State transitions
    async def freeze(
        self, *, caller, sub_id, frozen_until: date | None = None
    ) -> Subscription: ...

    async def unfreeze(
        self, *, caller, sub_id, auto: bool = False
    ) -> Subscription: ...
    # auto=True: called by the beat job; also auto-extends expires_at by the frozen duration.
    # Manual unfreeze does the same extension.

    async def renew(
        self, *, caller, sub_id, new_expires_at: date | None = None
    ) -> Subscription: ...
    # Default: pushes expires_at forward by plan.billing_period (monthly=30d, quarterly=90d, yearly=365d).
    # One-time plans: +duration_days.
    # Works on status IN (active, expired). Writes 'renewed' event with days_late on expired→active.

    async def change_plan(
        self, *, caller, sub_id, new_plan_id: UUID, effective_date: date | None = None
    ) -> Subscription: ...
    # Atomically: creates new sub (fresh price snapshot from new_plan),
    # marks old sub replaced+replaced_by_id, writes 'replaced' + 'changed_plan' events,
    # syncs Member.status to the new sub. Returns the NEW sub.

    async def cancel(
        self, *, caller, sub_id, reason: str | None = None
    ) -> Subscription: ...

    # Scheduled-job entrypoints (called by Celery beat)
    async def auto_unfreeze_due(self, *, tenant_id: UUID | None = None) -> int: ...
    async def auto_expire_due(self, *, tenant_id: UUID | None = None) -> int: ...
```

**Business rules enforced here:**

- **Tenant scoping** on every method (identical pattern to PlanService).
- **Price lock on create AND on change-plan:** service reads the new plan's `price_cents` + `currency` and writes them to the new row. Endpoints don't even accept a `price_cents` field.
- **Plan tenant match:** reject 422 if `plan.tenant_id != caller.tenant_id` (belt-and-suspenders against the FK).
- **Plan must be active on create / change-plan:** can't reference a deactivated plan. Existing subs on a plan that's deactivated later keep running unaffected.
- **`started_at` default** = today if null/omitted. Future dates allowed ("starts Monday").
- **`expires_at` semantics on create:**
  - Caller provides explicit `expires_at` = cash / prepaid-N-months / one-time use that value.
  - Caller omits + plan is one-time = auto-set to `started_at + plan.duration_days`.
  - Caller omits + plan is recurring = `NULL` (card-auto, runs until cancelled).
- **One-live-sub invariant** on create AND change-plan: checked at the service layer for a clean 409, enforced by the DB partial unique index as the last line of defense.
- **`change_plan` requires a different plan:** `new_plan_id == current.plan_id` raises `SamePlanChangeError` (409). Prevents ghost `replaced` rows that point to the same plan.
- **State-machine guards** on every transition — call the entity's `can_*` methods, raise `InvalidSubscriptionStateTransitionError` (409) if false.
- **Freeze extends `expires_at`:** when `unfreeze` runs (manual OR auto), service computes `frozen_days = today - frozen_at` and pushes `expires_at += frozen_days` (only if `expires_at` is set). Paused time doesn't eat paid time.
- **Renew math:**
  - If caller passes explicit `new_expires_at`, use it.
  - Otherwise, base date = `max(today, current.expires_at)` for `active`, or `today` for `expired`.
  - Extension = plan.billing_period days (monthly=30, quarterly=90, yearly=365) or plan.duration_days for one-time.
  - On `expired → active` renewals, compute `days_late = today - expired_at` and log in the event.
- **Member.status sync** in the same transaction as every state change (Option B above).
- **Event log write** in the same transaction as every state change (see `subscription_events`). One row per transition; no state change is ever "silent".
- **Role gates:** all mutations require `staff+`. Read methods require any tenant user.

**Scheduled jobs** (new Celery Beat entries):

- `auto_unfreeze_due` — runs daily 03:00 UTC. Finds `status='frozen' AND frozen_until <= today`, flips to `active`, extends `expires_at` by the frozen duration, syncs Member.status, writes `unfrozen` events (created_by=null). Returns count.
- `auto_expire_due` — runs daily 03:05 UTC. Finds `status='active' AND expires_at < today`, flips to `expired`, sets `expired_at = today`, syncs Member.status, writes `expired` events (created_by=null). Returns count.

Both jobs are idempotent (re-running finds zero new rows), bounded by the partial indexes, and emit structured logs + metrics.

---

## Frontend

### Feature folder

```
features/subscriptions/
├── api.ts                        # 11 functions (create, list, get, events, freeze, unfreeze, renew, change-plan, cancel + 2 member-scoped)
├── hooks.ts                      # TanStack Query wrappers + invalidation of ["subscriptions"] AND ["members"]
├── types.ts                      # re-exports from api-types
├── SubscriptionForm.tsx          # enroll: member picker + plan picker + dates + expires_at
├── SubscriptionFreezeDialog.tsx  # modal with optional frozen_until date
├── SubscriptionRenewDialog.tsx   # modal: default "+1 billing cycle", optional explicit date
├── SubscriptionChangePlanDialog.tsx  # modal: plan picker (must differ from current) + effective date
├── SubscriptionCancelDialog.tsx  # modal: common-reason dropdown + optional free-text
├── SubscriptionBadge.tsx         # reusable status badge (shared with member list)
├── SubscriptionTimeline.tsx      # renders events newest-first ("הוקפא", "חודש — 3 ימים איחור", ...)
└── *.test.tsx                    # full coverage
```

### Routing + integration

Subscriptions don't need their own top-level list page (`/subscriptions`) in v1 — they're always viewed in the context of a Member. The Member Detail page (`/members/:id`) gets a new section:

```
┌─── Member: דנה כהן ─────────────────────────────┐
│ [Identity — unchanged]                           │
│                                                  │
│ ── מנוי נוכחי ────────────────────────────────── │
│  תוכנית:      חודשי — 3 קבוצתי + 1 אישי         │
│  מחיר:         450 ₪ / חודש                      │
│  סטטוס:        [פעיל]                            │
│  תוקף עד:     1 במאי 2026                        │
│                                                  │
│  [חדש] [הקפא] [שנה מסלול] [בטל]                  │
│                                                  │
│ ── טיימליין ─────────────────────────────────── │
│  1 באפריל — נרשם לתוכנית "חודשי"                │
│  10 באפריל — הוקפא (עד 20 באפריל)                │
│  18 באפריל — הופשר ידנית                         │
│                                                  │
│ ── היסטוריית מנויים ──────────────────────────── │
│  [Past subs — plan, status, dates, replaced→]    │
└──────────────────────────────────────────────────┘
```

**New staff-only page: "מנויים שעומדים לפוג"** at `/subscriptions/expiring`. Simple filterable list of subs with `expires_at` in the next 7 days (configurable window). Lets staff batch-call members before they flip to `expired`.

The Member List page's status column shows the sub-derived status badge (same values, same colors — no visual change beyond the source of truth).

**Dashboard widgets** (MRR, expiring-this-week count, late-renewals-this-month, churn) land next milestone; the backend aggregate queries are ready after this PR.

### Error humanizer

`humanizeSubscriptionError(err)` in `lib/api-errors.ts`:
- 404 → "המנוי לא נמצא"
- 409 member-has-active-sub → "למנוי זה כבר יש מנוי פעיל"
- 409 state transition → "לא ניתן לבצע פעולה זו בסטטוס הנוכחי"
- 409 same-plan change → "יש לבחור מסלול שונה מהנוכחי"
- 422 → "הפרטים שהוזנו אינם תקינים"

### Permissions

`"subscriptions"` feature is NOT added to `accessibleFeatures` as a top-level item (no sidebar link). It's rendered inline in Member pages and guarded by the existing `members` feature — if you can see a member, you can see their sub.

If/when we add the top-level list page in v2, we add `"subscriptions"` to the Feature union and give it to owner + staff baseline.

---

## Tests

### Backend

| Type | File | Coverage target |
|---|---|---|
| Unit | `test_subscription_entity.py` | State-machine methods: `can_freeze`, `can_unfreeze`, `can_cancel`, `should_auto_unfreeze`, `should_auto_expire`, defaults |
| Integration | `test_subscription_repo.py` | CRUD, partial-unique-index rejects 2nd active, cross-tenant 404, filters (member/status/expires_before), ordering |
| E2E | `test_subscriptions.py` | Create as staff (201), create when member has active sub (409), create with cross-tenant plan (404/422), freeze→unfreeze→cancel happy path, invalid transitions (409), cancel persists reason, one_time plan gets `expires_at` auto-set, recurring plan gets `expires_at=NULL` |
| E2E | `test_subscription_jobs.py` | auto_unfreeze_due extends expires_at, auto_expire_due sets expired_at + writes event |
| E2E | `test_subscription_events.py` | Every state transition writes exactly one event row, created_by is set correctly, `days_late` computed on renew-from-expired |

Target: ~30 new backend tests.

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | Each function's URL/body/query-string (11 endpoints) |
| `SubscriptionForm.test.tsx` | Member + plan pickers, required fields, submit shape, expires_at handling |
| `SubscriptionFreezeDialog.test.tsx` | Open, submit with/without `frozen_until` |
| `SubscriptionRenewDialog.test.tsx` | Default +1 billing period, explicit date override, works on expired subs |
| `SubscriptionChangePlanDialog.test.tsx` | Plan picker, same-plan rejected, effective_date default today |
| `SubscriptionCancelDialog.test.tsx` | Common-reason dropdown + free text, confirm-destructive pattern |
| `SubscriptionTimeline.test.tsx` | Renders events in order, days_late pill on late renewals |
| `MemberDetailPage.test.tsx` | *(update)* Renders current sub, timeline, all action buttons per role |
| `api-errors.test.ts` | humanizeSubscriptionError for each status |

Target: ~25 new frontend tests + ~5 updates to existing member tests.

---

## Decisions

1. **Separate entity with its own lifecycle.** Not columns on Member — history + price lock + events justify the table.
2. **Member.status mirrors current-sub.status** (Option B). SubscriptionService is the writer; MemberService's freeze/cancel become delegators or get deprecated.
3. **One live sub per member** enforced by a partial UNIQUE index at the DB level, not just the service. Hard invariant.
4. **Price locked at create-time AND on change-plan.** Neither endpoint accepts a price field.
5. **No PATCH endpoint.** Every mutation is a named state transition (freeze/unfreeze/renew/change-plan/cancel).
6. **`cancelled` is HARD-terminal.** No transitions out. `replaced` is terminal for the OLD sub only (forwards to new sub via `replaced_by_id`). `expired` is SOFT-terminal — `renew` can resurrect it (same row, same price, tenure preserved).
7. **Expiry is core, not edge.** Cash-paid / prepaid members use `expires_at`; card-auto members use `NULL`. Nightly job flips `expires_at < today AND status='active'` → `expired` (NOT cancelled — different for retention reports).
8. **Freeze extends `expires_at`.** Industry standard — paused time doesn't eat paid time. Applied on unfreeze (manual or auto).
9. **Plan change via `replaced` status.** Old sub → `replaced` + `replaced_by_id` → new sub with fresh price snapshot. NOT counted as churn. Blocks same-plan changes (409).
10. **Renew works on `active` AND `expired`.** Preserves tenure and gives the owner `days_late` telemetry (members who renew late). `cancelled` cannot renew (that was an active departure).
11. **Auto-unfreeze + auto-expire are daily Celery jobs**, not on-access checks. Deterministic observability (countable "moved last night"), simpler tests, no read-path overhead.
12. **No grace-period state.** `expired` IS the grace signal; staff contacts members via the "about-to-expire" view before they flip.
13. **Cancel reason = optional dropdown + free text.** Common options (moved / too expensive / not using / injury / other) nudge staff for analytics without forcing a field.
14. **No entitlement usage tracking here.** "3 classes/week — how many used?" is Attendance (Phase 3). New sub = fresh quota window.
15. **Staff can cancel, renew, change-plan.** Owner-gating daily operations would block the gym.
16. **`subscription_events` table in v1.** Append-only timeline. Written inside the same transaction as every state change. Critical for retention analytics (the "my members forget, staff should call them" workflow).

---

## Open questions

All material design questions answered. A few implementation-time calls remain:

1. **MemberService refactor scope.** Delegate `freeze`/`cancel` to SubscriptionService, or deprecate the Member-level endpoints entirely? → Leaning deprecation + call-site migration in the same PR for a clean end state. If call-site churn blows up the PR size, delegate as a temporary bridge.
2. **Expiry job timezone.** `expires_at` is a DATE; "today" is ambiguous without a timezone. → Server UTC for v1. Israel is +2/+3, so a UTC-midnight job flips a sub one evening earlier than literal local-midnight — acceptable drift. Add per-tenant timezone if gyms in other regions care.
3. **"Current subscription" shape on Member responses.** Return the full nested sub object on `/members/{id}` (+ `/members`), or just `current_subscription_id`? → Leaning nested for `/members/{id}` (cuts a round-trip on the detail page) and just `id` on `/members` (keeps the list cheap). Revisit if lists need the price.
4. **`replaced_by_id` visibility in the UI v1.** Store the column, skip the "click to navigate to the replacing sub" UI until an owner asks. History table shows the `replaced` badge; that's enough info.

---

## Migration plan

**Single combined PR** (backend + frontend + Member.status sync) — per the "one-shot" call. ~500 LOC backend, ~400 LOC frontend, +spec/tests.

### Backend

1. Migration `0008_create_subscriptions.py` — `subscriptions` + `subscription_events` + all indexes + partial UNIQUE.
2. Domain entities: `Subscription`, `SubscriptionEvent` + enums + exceptions.
3. Repo: `SubscriptionRepository` (subs CRUD) + helper for event writes.
4. Service: `SubscriptionService` (all 11 methods) + Member.status sync.
5. Routes + schemas (11 endpoints).
6. Celery beat: `auto_unfreeze_due`, `auto_expire_due` tasks.
7. Member API: return nested `current_subscription` on detail endpoint.
8. MemberService refactor: deprecate or delegate `freeze`/`cancel` → decide during impl.
9. Tests: unit + integration + e2e + jobs + events.

### Frontend

1. Feature folder (`api.ts`, `hooks.ts`, `types.ts`, 5 dialogs, `SubscriptionTimeline`, `SubscriptionBadge`).
2. MemberDetailPage — current-sub section + timeline + all action buttons.
3. MemberListPage — status sourced from nested current_subscription.
4. New `/subscriptions/expiring` staff page (about-to-expire list).
5. Error humanizer + permissions.
6. Tests.

Estimate: ~2 days given state-machine complexity + jobs + event logging + Member refactor.

---

## Related docs

- [`spec.md`](../spec.md) §3.6 — Subscriptions in the product spec, §3.7 — Payments (next)
- [`members.md`](./members.md) — subject of the subscription; member.status sync pattern defined here
- [`membership-plans.md`](./membership-plans.md) — what's being subscribed to; price + currency snapshot source
- [`../standards/4-layer-example-users.md`](../standards/4-layer-example-users.md) — the 4-layer recipe we'll follow
- [`../skills/build-backend-feature.md`](../skills/build-backend-feature.md), [`../skills/build-frontend-feature.md`](../skills/build-frontend-feature.md)
