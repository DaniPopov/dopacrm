# Feature: Coaches

> **Status:** Planned. Spec for review — not yet implemented.
>
> **Order:** Build AFTER Attendance (shipped). BEFORE Payments is OK —
> coaches and payments touch money but don't collide (coaches estimate
> what the gym OWES; payments record what members PAY). A Schedule
> feature will land AFTER Coaches and upgrade the attribution math.
>
> **What this is:** the gym's coaches (boxing, wrestling, yoga, PT, ...),
> their assignment to classes, their pay rules per class, and a payroll
> estimate endpoint the owner uses to answer "how much do I owe this
> month?".

---

## Summary

Every feature before Coaches has been about the **gym's revenue side** —
who pays, for what, how often. Coaches is the first feature about the
gym's **cost side**. It turns the question "how much do we make?" into
"how much do we net?".

Concretely, this feature adds:

- A **`coaches` table** — the gym's coaches as first-class resources. A
  coach can (optionally) be linked to a `user` so they can log in and
  see their own classes + attendance + earnings. A coach without a
  linked user is just a record on the payroll — some gyms want that.
- A **`class_coaches` link table** — many-to-many between classes and
  coaches, with **per-link pay rules**. The same coach can be the head
  of boxing at ₪50/attendee AND an assistant in wrestling at ₪30/session.
- **Day-of-week teaching pattern per link** — a coach teaches class X on
  Sunday + Tuesday; a second coach teaches the same class on Wednesday.
  Used to attribute each check-in to the right coach without a full
  schedule feature.
- **`class_entries.coach_id`** — captured server-side at check-in via
  the weekday lookup. Immutable history. When Schedule ships, the same
  column will be populated from the schedule's session record instead.
- A **payroll estimate endpoint** — `GET /coaches/{id}/earnings?from=&to=`
  sums fixed salary + per-session + per-attendance pay across all the
  coach's (class) links in the date range.
- An **owner-facing Coaches page** — CRUD + "pay estimate this month"
  per coach.
- A **"Coaches" section on the Class detail page** — owner adds/removes
  coaches on a class, sets their role, pay rule, and weekdays inline.
- **A minimal coach-portal view baseline** — a coach user who logs in
  sees their own classes + attendance rosters + their earnings estimate.
  Nothing else. When dynamic roles (Phase 4) land, owner can flip this
  per-coach without changing `canAccess` call sites.

---

## Why it's a separate feature (not folded into Users or Classes)

- **Different lifecycle from users.** A coach can exist without a user
  row (no login). A user can exist without being a coach. The overlap is
  small — don't overload one table with two concepts.
- **Per-link business logic.** Pay rules are per (coach, class) — they
  don't live on the coach (who, overall) OR the class (which). The only
  place they fit is the link table.
- **Different permission gate.** Owner manages coaches; staff doesn't
  set pay rules. Coach users read only their own data. Attendance staff
  sees coach assignments but doesn't modify them.
- **It's where payroll lives.** Every gym's payroll flow starts here.
  Keeping it in its own feature folder makes "what does payroll look like?"
  a one-place lookup.

---

## Where this sits in Phase 2 / 3

```
  Phase 2 (Core CRM) — shipped:
    Members / Classes / Plans / Subscriptions / Attendance

  Phase 3 (Operations) — now:
    Coaches                    ← THIS DOC
    Payments
    Class schedule / sessions  (next — upgrades coach attribution)
    Leads

  Phase 4 (Flexibility):
    Dynamic roles → owner configures what each coach role sees
    Private workouts (1-on-1) → coaches with non-class pay rules
```

Coaches is a **Phase 3** feature even though it references Phase 2
entities (classes, attendance) everywhere. The ordering is: we can't do
Coaches without Attendance (no events to count); we CAN do Coaches
before Payments (they're independent numbers).

---

## User stories

1. **As an owner**, I open `/coaches` and see all my coaches, their
   classes at a glance, and an "estimated pay this month" number per
   coach. I add a new coach by typing their name + phone + optional
   email. If I also want them to be able to log in, I invite them → a
   `user` row is created, linked to the `coach` row.
2. **As an owner**, I open a class detail page and see a "Coaches"
   section. I pick a coach from the `AsyncCombobox`, set their role
   (free-form text — "ראשי", "עוזר", "night shift"), pick a pay model
   (fixed / per session / per attendance) and amount, and tick which
   weekdays they teach this class. Save.
3. **As an owner**, I open a coach's detail page → I see: all classes
   they teach (each as a small card with role + pay rule + weekdays),
   this month's attendance count across those classes, their current
   earnings estimate. I can freeze a coach (stops new pay accrual,
   keeps history) or reactivate them.
4. **As an owner**, on my dashboard (future), I see "total payroll this
   month" — sum of all coach earnings estimates.
5. **As a logged-in coach**, I see my classes, attendance counts, and my
   own earnings estimate for the current month. I cannot see other
   coaches, members' financial info, or the gym-wide payroll.
6. **As front-desk staff**, I don't interact with coaches directly — but
   every check-in I record gets a `coach_id` attached automatically
   based on the weekday pattern. No extra clicks.

**Explicitly NOT in this feature:**
- **Schedule / calendar view** — "spinning is on Monday 18:00 with
  Coach David" lands as the next feature. Weekly recurrence lives in
  `class_coaches.weekdays` for now; time-of-day doesn't exist yet.
- **Per-session substitutions** — the schedule-page substitution UI
  you and I discussed is the Schedule feature's job, not this one.
  For this PR, `class_entries.coach_id` is computed from the weekday
  pattern, full stop. If owner needs to correct a mis-attribution,
  it's an admin action (see §"Corrections" below).
- **Private / 1-on-1 workouts** — these pay differently (per session
  with a specific member, not per class). Needs its own entity. v2.
- **Payroll approval workflow** — "owner reviews + marks as paid + it
  becomes a real liability". This feature gives the ESTIMATE. Turning
  an estimate into an actual payout record is a Payments-side concern.
- **Multi-month contracts / raises** — fixed salary is stored as a
  single monthly amount. History of rate changes = separate table
  later. Today: editing the rate edits it going forward; past
  earnings stay as-computed.
- **Coach certifications / scheduling preferences** — owner-customizable
  `custom_attrs` JSONB is available but not wired into the UI yet.

---

## Decisions (baked in from the back-and-forth)

### 1. Coach identity — optional link to user, not a subclass

A coach is a **first-class row** in `coaches`. If the owner wants them
to log in, owner invites them → the create-user flow runs, a `users`
row is created with `role='coach'`, and the coach row's `user_id` FK
is set.

- Coach without user → exists on payroll, can't log in. That's fine.
- User without coach → a regular staff/owner/sales user. That's fine.
- User with coach link → logs in, sees coach portal baseline.

**Why not just `users.role='coach'` with a `is_coach` flag?**
- A coach may not want CRM access. Forcing a user row adds onboarding
  friction + an email field that may not exist.
- Pay rules, teaching days, role-on-class live on `class_coaches` —
  they belong next to the coach entity, not buried in the users table.
- Cleaner separation of concerns: users are "who can log in", coaches
  are "who teaches".

### 2. Pay rules live on the (coach, class) link

Every `class_coaches` row has its own `pay_model` + `pay_amount`. A
coach with two links has two different rates.

```
  Example — Coach David:
    class_coaches(david, boxing,  role='head',      pay=per_attendance, ₪50)
    class_coaches(david, wrestling, role='assistant', pay=per_session, ₪30)

  Earnings for a month:
    boxing:    sum(per_attendance: 50 × count_of_boxing_entries_on_david's_weekdays)
    wrestling: sum(per_session:    30 × distinct_days_with_entries_on_david's_weekdays)
    plus any fixed-pay links pro-rated.
```

### 3. `role` on the link is free-form text

Default suggestions in the UI: **"ראשי"** (head), **"עוזר"** (assistant).
Owner can type anything: "night-shift coach", "substitute only", etc.

Not an enum because gyms invent their own role names constantly, and
fixing an enum means every new gym either has to match ours or do
nothing. Free-form text + suggestions hits the sweet spot — typical
gyms use the defaults, weird gyms aren't blocked.

Reports group by the exact string. Not a big deal — a gym typically
has 3-4 distinct role labels max.

### 4. Pay models: `fixed` | `per_session` | `per_attendance`

- **`fixed`** — `pay_amount` is a **monthly salary**. Earnings query
  over a date range pro-rates by day count. Example: `₪3000/month`,
  queried for May 1–15 → `₪3000 × 15 / 31 = ₪1451`.
- **`per_session`** — `pay_amount` is paid each time the coach taught.
  In v1 (no Schedule), "a session happened" is approximated as "the
  coach had ≥1 attendance on that day". When Schedule lands, this
  switches to "count of non-cancelled sessions". See §"V1 → Schedule
  migration path".
- **`per_attendance`** — `pay_amount` × (count of effective check-ins
  attributed to this coach for this class in the date range).

Effective check-ins = `class_entries.undone_at IS NULL`. Override
entries **count** by default (owner can filter in the report).

### 5. Attendance attribution — `class_entries.coach_id`, immutable

**At check-in time (server-side, no UI):**
1. Compute `weekday = entered_at at Asia/Jerusalem`.
2. Find the `class_coaches` rows for `(entry.class_id, weekday in weekdays)`.
3. If **exactly one matches** → set `class_entries.coach_id = that.coach_id`.
4. If **multiple match** → set to the row with `is_primary=TRUE`. If no
   primary is set, deterministic-sort (coach_id ASC) and pick the first
   — better than leaving null, correction available.
5. If **none match** → fall back to `class_coaches` rows with
   `weekdays IS NULL OR weekdays = '{}'` (coach who teaches every day).
   If still ambiguous, leave `coach_id = NULL`. The earnings query
   ignores NULL-coach entries with a WARNING log event.

The column is **set once at insert time and never updated by the
service**. Changing `class_coaches.weekdays` later does NOT retroactively
change past entries — immutable payroll history.

**Corrections:** owner can call a single admin endpoint
`POST /api/v1/attendance/{entry_id}/reassign-coach` with a `coach_id`
body if a past entry was mis-attributed. Logged to structlog with
`attendance.coach_reassigned` event. Not exposed in front-desk UI.

**Why not compute at query time instead of storing?**
- Immutable history. Payroll cannot shift under the owner's feet just
  because the weekday pattern was edited three months later.
- Fast earnings queries — no join to `class_coaches` + weekday math
  for every entry; just `GROUP BY coach_id`.

### 6. Fixed pay pro-ration — by day, not by session-count

`₪3000/month` queried for a partial month returns
`3000 × (days_in_range / days_in_month)`, evaluated day-by-day so a
query spanning two months computes each month's slice separately and
sums them.

Not by "how many sessions happened in the range" because fixed pay is
by definition **not session-tied** — the coach is paid whether or not
a class ran. Pro-rating by day is the universal "salary-over-partial-
period" rule and what the owner expects on a pay stub.

### 7. Coach status — `active` / `frozen` / `cancelled`

Same pattern as members. `frozen` = no new pay accrual from this
moment onward, but historical earnings are untouched. Used when a coach
is on leave, injured, etc. `cancelled` is terminal — coach leaves the
gym. All states keep `class_coaches` rows intact for audit.

Earnings query filters: `frozen` coaches return 0 for dates after
`frozen_at`; `cancelled` return 0 for dates after `cancelled_at`.

### 8. Coach-portal baseline permissions

New `feature: "coaches"` added to the permissions module. Baseline:

| Feature | owner / super_admin | staff | sales | **coach** |
|---|---|---|---|---|
| `dashboard` | ✓ | ✓ | ✓ | ✓ (own classes + earnings) |
| `members` | ✓ | ✓ | ✓ | ✗ |
| `classes` | ✓ | ✓ | ✓ | ✓ (read — only classes they teach) |
| `attendance` | ✓ | ✓ | ✗ | ✓ (read — only their classes) |
| `plans` / `subs` / `payments` | ✓ | ✓ (except payments for staff) | ✓ | ✗ |
| `coaches` | ✓ | — | — | ✓ (own row read only) |

Enforcement today: hardcoded `canAccess` baseline. When dynamic roles
land, owner checkboxes flip rows in `tenant_roles.features[]`.
Call sites don't change.

---

## Data Model

### `coaches` table (migration `0011_create_coaches.py`)

```sql
CREATE TABLE coaches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,

  first_name TEXT NOT NULL,
  last_name  TEXT NOT NULL,
  phone      TEXT,
  email      TEXT,

  hired_at   DATE NOT NULL DEFAULT CURRENT_DATE,
  status     TEXT NOT NULL DEFAULT 'active'
             CHECK (status IN ('active','frozen','cancelled')),
  frozen_at     TIMESTAMPTZ,
  cancelled_at  TIMESTAMPTZ,

  custom_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT chk_frozen_shape
    CHECK ((status = 'frozen') = (frozen_at IS NOT NULL)),
  CONSTRAINT chk_cancelled_shape
    CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);

CREATE UNIQUE INDEX ux_coaches_user
  ON coaches(user_id) WHERE user_id IS NOT NULL;

CREATE INDEX idx_coaches_tenant ON coaches(tenant_id, status);
```

**Notes:**
- `user_id` is nullable + unique — a user can be linked to at most one
  coach row. A user without a linked coach row is a regular user.
- `status` shape-check mirrors Members — `frozen_at` / `cancelled_at`
  match the status.
- `custom_attrs` reserved for Phase 4 (certifications, pref. hours).
- No soft-delete on coaches — we use `status='cancelled'`, same as
  members/subs. Keeps the data model consistent.

### `class_coaches` table

```sql
CREATE TABLE class_coaches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id  UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  coach_id  UUID NOT NULL REFERENCES coaches(id) ON DELETE CASCADE,

  role         TEXT NOT NULL DEFAULT 'ראשי',
  is_primary   BOOLEAN NOT NULL DEFAULT FALSE,

  pay_model    TEXT NOT NULL
               CHECK (pay_model IN ('fixed','per_session','per_attendance')),
  pay_amount_cents INT NOT NULL CHECK (pay_amount_cents >= 0),

  -- Array of 3-letter lowercase day codes: 'sun','mon','tue','wed','thu','fri','sat'.
  -- Empty array = "all days" (coach can be attributed any day).
  weekdays TEXT[] NOT NULL DEFAULT '{}',

  starts_on DATE NOT NULL DEFAULT CURRENT_DATE,
  ends_on   DATE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT chk_range_valid
    CHECK (ends_on IS NULL OR ends_on >= starts_on)
);

-- One (class, coach, role) link per tenant — a coach can't be "head of
-- boxing" twice. They CAN be "head" AND "assistant" of boxing if the
-- owner really wants that (separate rows, separate pay rules).
CREATE UNIQUE INDEX ux_class_coaches_role
  ON class_coaches(class_id, coach_id, role);

-- At most one primary per (class, role) on any given day.
-- Enforced in service layer (weekday overlap check). Partial unique
-- won't express "arrays overlap"; service does the check.

CREATE INDEX idx_class_coaches_tenant ON class_coaches(tenant_id);
CREATE INDEX idx_class_coaches_class  ON class_coaches(class_id);
CREATE INDEX idx_class_coaches_coach  ON class_coaches(coach_id);
```

**Notes:**
- `pay_amount_cents` not `float`. Payroll wants integer arithmetic.
- `weekdays` as TEXT[] is ergonomic; querying uses
  `'sun' = ANY(weekdays)`. Empty array = catch-all (coach teaches
  whenever an entry lands).
- `starts_on` / `ends_on` let the owner express "this rate applies
  from X to Y". A rate change = end the old row (`ends_on = today-1`),
  insert a new one. Earnings queries clip to the rate-row's range
  automatically. Primitive version of contract-history.

### `class_entries.coach_id` (migration adds column)

```sql
ALTER TABLE class_entries
  ADD COLUMN coach_id UUID REFERENCES coaches(id) ON DELETE SET NULL;

CREATE INDEX idx_entries_coach_entered
  ON class_entries(coach_id, entered_at DESC)
  WHERE undone_at IS NULL AND coach_id IS NOT NULL;
```

- Nullable for backfill + cases where no `class_coaches` row matches.
- `ON DELETE SET NULL` — if a coach row is deleted outright (very rare
  — we prefer `status='cancelled'`), the history isn't orphaned.
- Partial index targets the only query that uses it — earnings, which
  filters out undone + null-coach entries.

**Backfill:** a one-shot script (`backend/scripts/backfill_class_entry_coaches.py`)
re-runs the weekday lookup against existing rows. Safe to re-run —
idempotent on `coach_id IS NULL`.

---

## Domain (Layer 3)

**`domain/entities/coach.py`**

```python
class CoachStatus(StrEnum):
    ACTIVE    = "active"
    FROZEN    = "frozen"
    CANCELLED = "cancelled"

class Coach(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None

    first_name: str
    last_name: str
    phone: str | None
    email: str | None

    hired_at: date
    status: CoachStatus
    frozen_at: datetime | None
    cancelled_at: datetime | None

    custom_attrs: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def is_active(self) -> bool:
        return self.status == CoachStatus.ACTIVE

    def can_freeze(self) -> bool:
        return self.status == CoachStatus.ACTIVE

    def can_unfreeze(self) -> bool:
        return self.status == CoachStatus.FROZEN

    def can_cancel(self) -> bool:
        return self.status in (CoachStatus.ACTIVE, CoachStatus.FROZEN)
```

**`domain/entities/class_coach.py`**

```python
class PayModel(StrEnum):
    FIXED           = "fixed"
    PER_SESSION     = "per_session"
    PER_ATTENDANCE  = "per_attendance"

WEEKDAYS = ("sun","mon","tue","wed","thu","fri","sat")

class ClassCoach(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    coach_id: UUID
    role: str
    is_primary: bool
    pay_model: PayModel
    pay_amount_cents: int
    weekdays: list[str]           # subset of WEEKDAYS; [] = all days
    starts_on: date
    ends_on: date | None

    @field_validator("weekdays")
    def _valid_weekdays(cls, v):
        for w in v:
            if w not in WEEKDAYS:
                raise ValueError(f"invalid weekday: {w!r}")
        if len(set(v)) != len(v):
            raise ValueError("duplicate weekday")
        return v

    def covers(self, d: date) -> bool:
        """True if this link was active on date d AND teaches on that weekday."""
        if d < self.starts_on: return False
        if self.ends_on is not None and d > self.ends_on: return False
        if not self.weekdays: return True
        return WEEKDAYS[ (d.weekday() + 1) % 7 ] in self.weekdays
```

**Exceptions** (added to `domain/exceptions.py`):
- `CoachNotFoundError` → 404
- `CoachStatusTransitionError` → 409
- `ClassCoachLinkNotFoundError` → 404
- `ClassCoachConflictError` → 409 (two primaries on overlapping weekdays)
- `InvalidPayModelError` → 422

---

## Payroll math — the interesting part

`AttendanceService` stays unchanged (entries still insert the same way;
the `coach_id` attribution is a small server-side hook in `record_entry`).

`CoachService.earnings_for(coach_id, from, to)` pseudocode:

```python
def earnings_for(coach_id, from_: date, to: date) -> EarningsBreakdown:
    coach = get_coach(coach_id)
    if coach.status == CANCELLED and coach.cancelled_at < from_:
        return EarningsBreakdown.zero()   # whole window is post-termination

    # 1. Clip the window to coach's active lifespan.
    effective_from = max(from_, coach.hired_at)
    effective_to   = min(to, coach.cancelled_at.date() if coach.cancelled_at else to)
    if coach.status == FROZEN and coach.frozen_at.date() < effective_to:
        effective_to = coach.frozen_at.date() - timedelta(days=1)
    if effective_to < effective_from:
        return EarningsBreakdown.zero()

    links = list_class_coaches_for(coach_id)           # all their links
    total_cents = 0
    by_class = defaultdict(int)

    for link in links:
        # Clip each link's rate-window to the effective window.
        span_from = max(effective_from, link.starts_on)
        span_to   = min(effective_to, link.ends_on or effective_to)
        if span_to < span_from: continue

        if link.pay_model == FIXED:
            # Monthly salary, pro-rated by day.
            cents = fixed_prorated(link.pay_amount_cents, span_from, span_to)
        elif link.pay_model == PER_SESSION:
            # v1: count distinct days the coach had ≥1 attributed entry
            # in THIS class on a weekday the link covers.
            days = count_distinct_days_with_entries(
                coach_id=link.coach_id,
                class_id=link.class_id,
                since=span_from, until=span_to,
                only_on_weekdays=link.weekdays,
            )
            cents = days * link.pay_amount_cents
        elif link.pay_model == PER_ATTENDANCE:
            n = count_effective_entries(
                coach_id=link.coach_id,
                class_id=link.class_id,
                since=span_from, until=span_to,
            )
            cents = n * link.pay_amount_cents

        total_cents += cents
        by_class[link.class_id] += cents

    return EarningsBreakdown(
        coach_id=coach_id,
        from_=from_, to=to,
        total_cents=total_cents,
        by_class=dict(by_class),
        currency=coach.tenant.currency,
    )


def fixed_prorated(monthly_cents, span_from, span_to) -> int:
    """Prorate monthly cents over a span that may cross month boundaries.

    For each calendar month touched by [span_from, span_to]:
        overlap_days = days in (month ∩ span)
        cents += monthly_cents * overlap_days / days_in_that_month
    Round once at the end.
    """
    ...
```

### Edge cases the math must handle

- Span crosses a month boundary → split & sum (covered by
  `fixed_prorated`).
- Rate change mid-month → two `class_coaches` rows, old one
  `ends_on = yesterday`, new one `starts_on = today`. Each link's span
  is clipped; both contribute correctly.
- Coach frozen mid-period → earnings truncate at `frozen_at`.
- Coach cancelled mid-period → same.
- Leap years → `days_in_month(Feb 2024) = 29` — use Python's calendar,
  not a constant.
- Override entries → count by default (`undone_at IS NULL`). Report
  includes a breakdown of overrides so owner can spot anomalies.

---

## API Endpoints

### Coaches CRUD

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/coaches` | owner+ | Create a coach. Body: `{first_name, last_name, phone?, email?, user_id?}` |
| GET | `/api/v1/coaches` | Bearer | List (filter: `status`, `class_id`, search by name). Coach user: only their own row. |
| GET | `/api/v1/coaches/{id}` | Bearer | Detail. Coach user: only their own row. |
| PATCH | `/api/v1/coaches/{id}` | owner+ | Partial update. |
| POST | `/api/v1/coaches/{id}/freeze` | owner+ | Set `status='frozen'`. |
| POST | `/api/v1/coaches/{id}/unfreeze` | owner+ | Return to `active`. |
| POST | `/api/v1/coaches/{id}/cancel` | owner+ | Terminal — coach leaves. |
| POST | `/api/v1/coaches/{id}/invite-user` | owner+ | Creates a `user` row with `role='coach'` + password setup; links `coaches.user_id`. Idempotent if already linked. |

### Class ↔ Coach links

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/classes/{class_id}/coaches` | owner+ | Assign a coach. Body: `{coach_id, role, is_primary, pay_model, pay_amount_cents, weekdays[], starts_on?, ends_on?}` |
| GET | `/api/v1/classes/{class_id}/coaches` | Bearer | List coaches on this class. |
| GET | `/api/v1/coaches/{id}/classes` | Bearer | List classes this coach teaches. |
| PATCH | `/api/v1/class-coaches/{link_id}` | owner+ | Edit pay rule, role, weekdays. Ending a rate window = PATCH `ends_on`. |
| DELETE | `/api/v1/class-coaches/{link_id}` | owner+ | Hard-delete link. Past `class_entries.coach_id` unchanged (FK ON DELETE SET NULL doesn't fire — the COACH row isn't deleted). |

### Earnings + admin

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/coaches/{id}/earnings?from=YYYY-MM-DD&to=YYYY-MM-DD` | owner+ or self | Payroll estimate for the range. Returns `{total_cents, by_class, by_pay_model, overrides_counted, currency}`. |
| GET | `/api/v1/coaches/earnings/summary?from=&to=` | owner+ | All coaches, one row each. Dashboard "total payroll this month" sums this. |
| POST | `/api/v1/attendance/{entry_id}/reassign-coach` | owner+ | Admin correction. Body: `{coach_id}` or `{coach_id: null}`. Logs `attendance.coach_reassigned`. |

**Why no PATCH on `class_entries.coach_id` via the generic route?**
`class_entries` is append-only (cf. Attendance spec). We expose
`reassign-coach` as an explicit owner-only action rather than opening
the general PATCH — makes the audit trail obvious.

---

## Frontend

### Feature folder

```
features/coaches/
├── api.ts
├── hooks.ts
├── types.ts                     # re-exports from api-types
├── CoachListPage.tsx            # /coaches (owner: full list; coach user: redirect to own detail)
├── CoachDetailPage.tsx          # /coaches/:id — classes + earnings + status actions
├── CoachForm.tsx                # create + edit
├── ClassCoachInlineForm.tsx     # used inside ClassDetailPage
├── ClassCoachesSection.tsx      # "Coaches" section on ClassDetailPage
├── EarningsCard.tsx             # total + breakdown by class
├── WeekdaysPicker.tsx           # 7-button strip (dual-use: coaches + future schedule)
└── *.test.tsx
```

### Routes + permissions

- `/coaches` — new route. `feature: "coaches"`.
- `/coaches/:id` — detail.
- Class detail page gets a **"מאמנים"** section below entitlements.
- Sidebar: **"מאמנים"** entry appears below "שיעורים" for owner, and at
  the top for a logged-in coach (it's their home).

Permissions added to `features/auth/permissions.ts`:
- New `Feature`: `"coaches"`.
- New `Role` value: `"coach"`.
- `accessibleFeatures("coach")` → `["dashboard","classes","attendance","coaches"]`,
  all with read-only modifiers enforced in the service layer.
- Existing `canAccess` call sites don't change.

### Shared UI primitives reused

- **`AsyncCombobox`** for picking a coach on the class page.
- **`ConfirmDialog`** for freeze / unfreeze / cancel confirmations.
- **`DataTable`** for the coach list.
- **`PageHeader`** + **`SectionCard`** to match the rest of the CRM.

### Error humanizer

`humanizeCoachError` in `lib/api-errors.ts`:
- 409 `status_transition` → "לא ניתן לבצע פעולה זו על מאמן בסטטוס הנוכחי"
- 409 `class_coach_conflict` → "יש כבר מאמן ראשי בשיעור זה בימים שבחרת"
- 422 `invalid_pay_model` → "מודל תשלום לא תקין"
- 422 generic → "הפרטים שהוזנו אינם תקינים"

---

## Observability

Structured log events (structlog JSON → stdout → CloudWatch Logs in prod):

| Event | Fields | When |
|---|---|---|
| `coach.created` | tenant_id, coach_id, user_id? | Create |
| `coach.status_changed` | tenant_id, coach_id, from, to, by | Freeze / unfreeze / cancel |
| `coach.class_assigned` | tenant_id, coach_id, class_id, role, pay_model, weekdays | Link created |
| `coach.class_rate_changed` | tenant_id, coach_id, class_id, old_model, old_amount, new_model, new_amount | Link PATCH that changes pay |
| `coach.earnings_queried` | tenant_id, coach_id, from, to, total_cents, by_caller | Owner runs an earnings report |
| `attendance.coach_attributed` | tenant_id, entry_id, coach_id, method='weekday'|'primary'|'fallback'|'null' | Every check-in |
| `attendance.coach_reassigned` | tenant_id, entry_id, old_coach_id, new_coach_id, by | Owner correction |

**Why `attendance.coach_attributed` fires on every check-in:** this is
a new automatic behavior. If the attribution logic has a bug, we need
to see it in the logs on day one.

---

## Tests

### Backend

| Type | File | Coverage target |
|---|---|---|
| Unit | `test_coach_entity.py` | Status transitions (freeze ↔ unfreeze, cancel is terminal), `is_active` |
| Unit | `test_class_coach_entity.py` | `covers()` weekday math, date-range checks, invalid weekdays |
| Unit | `test_earnings_math.py` | Pro-rating across month boundary, leap year, rate change mid-range, frozen-mid-range truncation, per-session distinct-day count, per-attendance with overrides |
| Integration | `test_coach_repo.py` | CRUD, cross-tenant isolation, status filters |
| Integration | `test_class_coach_repo.py` | Link CRUD, `ux_class_coaches_role` collision, list by coach + by class |
| E2E | `test_coaches.py` | Full CRUD round-trip, link assign, earnings happy path, coach user sees only own data, reassign-coach endpoint, cross-tenant probes |
| E2E | `test_attendance_coach_attribution.py` | Record entry → `coach_id` set from weekday → earnings math agrees; multiple primaries → deterministic pick; no match → null coach + log |

Target: ~35 new backend tests + ~10 additions to
`test_cross_tenant_isolation.py` (every coach endpoint gets a probe).

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | All endpoints (shape + URL) |
| `CoachListPage.test.tsx` | Rows render, filter by status, earnings-this-month column |
| `CoachDetailPage.test.tsx` | Classes list, earnings card, freeze/unfreeze/cancel via ConfirmDialog |
| `CoachForm.test.tsx` | Required fields, optional user invite button |
| `ClassCoachInlineForm.test.tsx` | Pay model select + amount + weekdays picker, validation |
| `WeekdaysPicker.test.tsx` | Toggle all 7 days, empty = all-days semantics |
| `EarningsCard.test.tsx` | Renders breakdown, currency formatting |
| `permissions.test.ts` (additions) | Coach baseline features, staff sees no coaches page |

Target: ~25 new frontend tests.

### Load test

`loadtests/test_coaches_load.py`:
- `OwnerDashboardWatcher` VU — polls `/coaches/earnings/summary` every
  5s (mimics a dashboard open). 2 VU for 60s.
- `CoachPortal` VU — polls `/coaches/{me}/earnings` + `/coaches/{me}/classes`
  — mimics a coach with the app open. 5 VU.
- Target: 99p earnings/summary < 150ms at 10 VU total, zero errors.

Added as `make load-test-coaches`.

---

## V1 → Schedule migration path

When the Schedule feature lands, these are the surgical swaps that
happen — none of them break existing data:

1. `class_sessions` table ships. One row per scheduled session with
   `(class_id, starts_at, ends_at, coach_id, assistant_coach_id, status)`.
2. `AttendanceService.record_entry` looks up the active session first;
   if found, uses its `coach_id`. Falls back to `class_coaches.weekdays`
   if no session is defined. Fall back never removed — it handles
   drop-in / unscheduled events.
3. Per-session pay math switches from "distinct days with entries" to
   "count of non-cancelled sessions". Zero change to the API shape.
4. Substitution UI lives on the Schedule week view — swap a session's
   `coach_id`, hit save. No check-in flow changes.
5. `class_entries.coach_id` remains immutable history. Future sessions
   write it from `class_session.coach_id`; past ones keep their
   weekday-derived value.

All of this lands as a separate PR. Coaches is complete without it.

---

## Open questions (to revisit during implementation)

1. **`coach_id` on `class_entries.subscription_id` side** — should the
   owner audit show "coach X got paid from entries on subscription
   Y"? Only useful if the gym disputes a specific member's
   attendance. Skip v1; revisit if asked.
2. **Per-coach currency?** Today every tenant has one currency — coach
   earnings inherit `tenant.currency`. If a tenant ever supports
   multi-currency billing (doubtful), this splinters.
3. **Earnings caching.** Summary query = N coaches × ~3 links × window
   math. For a 20-coach gym, that's ~60 COUNT queries on a date range
   index. Probably fine; confirm with load test before over-engineering.
4. **Rate-change audit.** Today editing a `class_coaches` row overwrites
   `pay_amount_cents` if the owner doesn't split into two rows. Do we
   want to FORCE the "end + new" pattern in the UI? Leaning yes —
   protects payroll history from accidental edits.
5. **Multi-location** — when a gym has two branches (Phase 2 of
   tenants), a coach may work at both. Today each branch is its own
   tenant → the coach exists twice. Leave for the multi-location
   effort.

---

## Migration plan

Single combined PR — backend + frontend — same shape as Subscriptions
and Attendance. Estimate: **2 days** given the payroll math + UI.

**Backend:**
1. Migration `0011_create_coaches.py` — coaches + class_coaches + `class_entries.coach_id`.
2. Domain entities + exceptions + unit tests.
3. Repositories (coach + class_coach + attendance query extensions).
4. `CoachService` — CRUD, status transitions, earnings math.
5. `AttendanceService.record_entry` — hook in the coach attribution.
6. `POST /api/v1/attendance/{id}/reassign-coach` endpoint.
7. `POST /api/v1/coaches/{id}/invite-user` — creates user + links row.
8. Routes + schemas.
9. E2E tests + cross-tenant probes.
10. Backfill script for existing `class_entries`.

**Frontend:**
1. Feature folder with pages/components above.
2. Permissions + sidebar + route guards.
3. `humanizeCoachError`.
4. "מאמנים" section wired on ClassDetailPage.
5. Tests.

**Docs / spec:**
1. `docs/spec.md` §3 gains a Coaches module.
2. `docs/crm_logic.md` captures the attribution + earnings rules so
   future features (Payments, Schedule) don't re-derive them.
3. `docs/features/coaches.md` — this doc, authoritative.

---

## Related docs

- [`spec.md`](../spec.md) — product-level overview, roadmap.
- [`crm_logic.md`](../crm_logic.md) — cross-feature business rules
  (attribution, pay-model math, state-machine rules).
- [`classes.md`](./classes.md) — classes, the entity coaches attach to.
- [`attendance.md`](./attendance.md) — attendance events, which carry
  `coach_id` and drive per-attendance earnings.
- [`roles.md`](./roles.md) — the dynamic-roles future that will let
  owners customize what each coach sees.
