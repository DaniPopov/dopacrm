# Feature: Schedule

> **Status:** Planned. Spec for review — not yet implemented.
>
> **Order:** Build AFTER Coaches (shipped). Ships WITH the Feature
> Flags mechanism — Schedule is a gated feature, OFF by default for
> new tenants.
>
> **What this is:** a weekly calendar of when classes run, who teaches
> them, who covered when someone was sick, and which sessions were
> cancelled. **Upgrades coach attribution** from the v1 weekday
> pattern to per-session truth.

---

## Summary

Schedule is the feature that turns the gym's **operational week** into
structured data. Until now the only signal about "when does boxing
run?" was:

- `classes.name = 'Boxing'` — what exists
- `class_coaches.weekdays = ['sun','tue']` — rough days a coach teaches
- `class_entries.entered_at` — when a member actually walked in

None of that answers: *is there a boxing session at 18:00 tomorrow? If
so, who's teaching? If someone is out sick next Tuesday, how does the
owner note the substitution?* Schedule is that answer.

Concretely, this feature builds:

- **A `/schedule` page** — weekly grid view, navigable by week,
  showing every session with its coach + status.
- **Recurring templates** (`class_schedule_templates`) — "boxing, Sun
  + Tue, 18:00–19:00, head = David, assistant = Yoni."
- **Materialized sessions** (`class_sessions`) — one row per concrete
  occurrence of a class. The template creates 8 weeks ahead; a Celery
  beat job extends the horizon nightly.
- **Individual session edits** — cancel this Tuesday's boxing, swap
  Yoni for Amir for Sunday's class.
- **Bulk range edits** — "cancel all boxing sessions from March 1 to
  March 14" (coach vacation).
- **Attendance attribution upgrade** — `class_entries.session_id` FK.
  At check-in, the system finds the active session for the class and
  stamps `session_id` + `coach_id = session.head_coach_id`. Weekday
  fallback stays for drop-ins with no scheduled session.
- **Per-session pay math cleanup** — `per_session` pay now counts
  non-cancelled scheduled sessions the coach was assigned to,
  replacing the v1 "distinct days with ≥1 entry" approximation.

---

## Why it's a separate feature (not folded into Coaches)

- **Different write pattern.** `class_coaches` changes when a coach
  joins the gym. `class_sessions` changes every week as the calendar
  fills, shifts, or cancels. Mixing them pollutes either table.
- **Different read pattern.** A calendar view query is
  `WHERE starts_at BETWEEN :start AND :end` — a time-range scan.
  `class_coaches` is lookup-by-key. Separate tables = separate indexes.
- **Different lifecycle.** A coach row lives for years; a session row
  lives for two weeks (the visible window) and then becomes historical
  payroll data. Archiving policies differ.
- **Different permission gate.** Schedule is gated behind its own
  feature flag. Coaches can be on without Schedule (weekday
  attribution works). Schedule without Coaches doesn't make sense,
  but the guard is explicit in the service layer.

---

## Where this sits in Phase 3

```
  Phase 2 (Core CRM) — shipped:
    Members / Classes / Plans / Subscriptions / Attendance

  Phase 3 (Operations):
    Coaches                 ✓ shipped
    Schedule                ← THIS DOC
    Feature Flags           ← shipped WITH this PR
    Payments                (next)
    Leads                   (after Payments)
```

Schedule is Phase 3 because it's the first feature whose raw data
(who taught when) only becomes valuable once you want to **run the
gym's operations**, not just its billing.

---

## User stories

1. **As an owner**, I open `/schedule` and see this week's gym — every
   class as a card on the grid, color-coded by class, with the coach's
   name and a 🚫 mark if cancelled. I can scroll to next week, last
   week, any week.
2. **As an owner**, my head boxing coach is on vacation March 1–14. I
   click **"בחר טווח"**, pick boxing, pick March 1–14, and choose
   *"swap coach → Yoni"*. All 4 sessions in that range now show Yoni
   as the teacher. One click, not four.
3. **As an owner**, I need to cancel tomorrow's 6:00 yoga because of
   a plumbing emergency. I click the session → "בטל שיעור" → reason
   → save. The session is marked cancelled; payroll doesn't count it;
   the check-in page won't attribute any walk-ins to this coach.
4. **As an owner**, I add a one-off "special workshop" Sunday 19:00
   with a visiting trainer. I click **"+ שיעור חד-פעמי"**, pick class,
   pick time, pick coach, save. A single ad-hoc session appears on
   the grid with no template backing it.
5. **As an owner**, I changed my boxing template from 18:00 to 19:00.
   Future materialized sessions (that I haven't manually touched)
   shift to 19:00 automatically. The 3 sessions I customized last
   month stay at 18:00 — my manual edits aren't stomped.
6. **As staff**, I walk over to the check-in page at 18:15 Tuesday. I
   pick a member + boxing. Behind the scenes, the system finds
   Tuesday's 18:00 boxing session and attributes the entry to
   David (the scheduled coach). My flow is unchanged.
7. **As a coach** (logged in), I see a simplified calendar of just my
   own sessions — "you have 3 sessions this week: Sun 18:00, Tue
   18:00, Thu 18:00, all boxing." I can't edit anything.
8. **As super_admin**, I toggle the Schedule feature ON for a new
   gym from `/tenants/{id}` → Features. It appears in their sidebar
   after they refresh.

**Explicitly NOT in this feature:**

- **Coach self-service edits.** Coaches view their schedule read-only.
  If they need a swap, they ask the owner (out-of-band). Workflow to
  request + approve lives with the coach portal v2.
- **Member-facing schedule / booking.** Members don't see the
  schedule. When the member portal ships, this feature's data is
  the source of truth for a read-only member view.
- **Waitlists + capacity limits.** A session doesn't enforce a max
  headcount. Gyms that need this get it in a follow-up.
- **Recurring-exception templates.** E.g. "cancel boxing every
  Tuesday for the next 4 weeks" — the bulk action covers this for
  a date range; proper recurring exceptions (like Google Calendar's
  "this and all following") is v2.
- **iCal / Google Calendar export.** Export flow lives on its own in
  a future integration PR.
- **Room / location assignment.** Gyms with multiple rooms don't get
  to specify which room per session. Classes are logical — "which
  class type?" — not physical. Multi-room is multi-tenant territory.
- **Session-level pricing / add-ons.** A session doesn't have a
  price. Members pay via their subscription; walk-ins pay via a
  one-time plan (existing). Future drop-in-per-session flow is
  Payments territory.

---

## Decisions (baked in from the back-and-forth)

### 1. Recurrence model — templates + materialized rows

- Owner creates a **template** (recurring rule).
- On create, the backend **materializes 8 weeks of sessions** from
  the template.
- A **Celery beat job** runs nightly and extends the horizon so
  there's always ~8 weeks of future visibility.
- On template **edit**, future sessions that haven't been manually
  customized re-materialize with the new values. Customized sessions
  (cancelled or substituted) stay frozen.

**Why this instead of "compute from template at query time"?**

- Queries become cheap `SELECT` against `class_sessions`.
- Customizations (cancel, swap coach) have a natural row to update.
- Historical truth is immutable: "at 18:00 on 2026-05-12, David
  was scheduled to teach boxing" is a row, not a recomputation
  that could yield a different answer after the template changes.
- Attendance attribution reads the session directly — no
  template-expansion logic in the hot path.

**Why not per-request materialization (lazy)?**

- Introduces a race condition between "session exists" and "session
  is customized." Cleaner to materialize eagerly.
- Beat job extending 4 weeks every night is a 5-line Celery task.

### 2. Time model — TIMESTAMPTZ, UTC storage, Asia/Jerusalem display

- `class_sessions.starts_at TIMESTAMPTZ` and `ends_at TIMESTAMPTZ`.
- Storage in UTC. Frontend converts via tenant's timezone (hardcoded
  `Asia/Jerusalem` today, `tenants.timezone` column later).
- DST: UTC storage means DST "just works" — a session at 18:00
  Jerusalem on one side of a DST change is still at 18:00 Jerusalem
  after. Template materialization computes the UTC timestamp for each
  date independently, so the math is correct across transitions.
- Duration is derived from `ends_at - starts_at`. We store both
  endpoints because that's what queries want ("what's running at
  18:30?") more often than duration in isolation.

### 3. Coach assignment — two slots per session

- `head_coach_id UUID NOT NULL` — the coach who gets paid for
  per-session / per-attendance.
- `assistant_coach_id UUID NULL` — optional second coach.
- **Not an N-coach array.** Owner surveys support 99% head+assistant,
  and the data model aligns with how pay attribution thinks
  ("who gets credit?"). If 3+ coaches ever become real, a
  `class_session_coaches` link table slots in.

Attribution uses `head_coach_id`. The assistant is present for
scheduling / visibility / future bulk payroll refinements.

### 4. Status — `scheduled` vs `cancelled`, "completed" is derived

- `status TEXT CHECK (status IN ('scheduled', 'cancelled'))`.
- "Completed" is NOT a stored status — it's `status='scheduled' AND
  ends_at < now()`. Derived, not mutated.
- Cancellation is terminal. `uncancelling` = admin-edit → create a
  new session. Keeps the event trail honest.

**Why not a richer state machine (in_progress, missed, etc.)?**

- Empty value. The gym owner doesn't care if "right now" a session
  is "in progress" — the clock tells them that.
- Missed sessions = zero attendances. That's a query, not a status.

### 5. Cancellation pay — NO pay by default (decision A)

- Per-session pay counts `status='scheduled'` only.
- Cancelled sessions contribute 0 cents to the coach's pay.
- **If the owner wants to make it up** (compassionate pay for a
  plumbing cancellation), that's a manual Payments entry (future).
  We don't model "cancelled but paid" as a session state because
  the edge case is rare and Payments already has a corrective flow.

### 6. Drop-in with no scheduled session — permissive (decision B)

- Check-in succeeds regardless of whether a session exists.
- `class_entries.session_id = NULL` in that case.
- Coach attribution falls back to the v1 weekday pattern (still
  present in the code as the fallback branch). If that also fails
  (no class_coaches row), coach_id stays NULL.
- `attendance.coach_attributed` structlog event records which path
  fired (`session` / `weekday` / `null`), so the owner can audit
  "how many entries last month had no scheduled session?".

### 7. Template edits re-materialize future non-customized sessions (decision E)

- Template edit triggers an **idempotent re-materialization** of
  sessions in the horizon.
- For each future session that matches the (template_id,
  original_date):
  - If the row is `status='cancelled'` → leave as-is.
  - If the row's `head_coach_id` or `assistant_coach_id` differs
    from the template (i.e. was manually substituted) → leave as-is.
  - If `starts_at` was manually edited (`is_customized=TRUE` flag) →
    leave as-is.
  - Otherwise → update `starts_at`, `ends_at`, `head_coach_id`,
    `assistant_coach_id` from the template.
- `is_customized` boolean on the session row tracks this. Set to
  TRUE by any service mutation (cancel, swap, time-edit). Cleared
  on re-materialization only if owner explicitly says
  "revert this session to template defaults" (future; not in v1).

### 8. Bulk range action — owner-friendly

- A modal: pick a class + date range + action (cancel OR swap coach).
- Server applies the action to every `status='scheduled'` session
  in the range. Single endpoint, single transaction:
  `POST /api/v1/schedule/bulk-action`.
- All affected sessions get `is_customized=TRUE`.
- Structlog `schedule.bulk_action` event carries the full list of
  affected session IDs so the audit is complete.

### 9. Auto-extend beat job

- Celery beat task runs nightly at 02:00 UTC.
- For each active template: find the latest materialized session's
  date. If it's less than 6 weeks out, materialize another 4 weeks.
- Backoff baked in: if the DB is slow, the next night catches up.
- Monitoring: `schedule.horizon_extended` event with
  `sessions_created` count per tenant.

### 10. Attribution upgrade — session_id > weekday > null

```
def attribute_coach(tenant_id, class_id, at):
    # 1. Is there a scheduled, non-cancelled session that overlaps `at`?
    session = find_session(
        tenant_id, class_id,
        starts_at ≤ at + 30min AND ends_at + 30min ≥ at,
        status='scheduled',
    )
    if session:
        return session.head_coach_id, "session", session.id

    # 2. Fallback: weekday pattern via class_coaches (v1 logic).
    coach_id = attribute_via_weekday(tenant_id, class_id, at)
    if coach_id:
        return coach_id, "weekday", None

    # 3. Nothing matched.
    return None, "null", None
```

- 30-minute tolerance on both edges lets members arrive a bit early
  / leave a bit late without breaking attribution.
- If multiple sessions overlap (weird — two classes at the same
  time in different rooms, hitting the same `class_id`), pick the
  one whose `starts_at` is closest to `at`.

### 11. Per-session pay math — upgrade

Before (v1): `count(distinct day with ≥1 attributed entry)`
After (now): `count(sessions where status='scheduled' AND head_coach_id=coach AND starts_at in range)`

Zero frontend change. Zero endpoint change. Just the service-layer
query. `CoachService.earnings_for` branches on "is Schedule enabled
for this tenant?" — if yes, use the new query; if no, keep the v1
approximation.

### 12. Feature flag — OFF by default, gated at service layer

- `tenants.features_enabled.schedule` boolean.
- Every mutation + read in `ScheduleService` starts with
  `is_feature_enabled(tenant, "schedule")` → `FeatureDisabledError`.
- Attendance attribution's session lookup is gated too — if
  Schedule is off, skip the session branch and go straight to
  weekday. Single-line `if`.

---

## Data Model

### Migration 0012 (combined with feature flags)

### `class_schedule_templates` table

```sql
CREATE TABLE class_schedule_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,

  -- Which weekdays the class runs. Lowercase 3-letter codes.
  weekdays TEXT[] NOT NULL CHECK (cardinality(weekdays) > 0),

  -- Time-of-day boundaries (NOT a timestamp — just HH:MM).
  start_time TIME NOT NULL,
  end_time   TIME NOT NULL,

  -- Default coach assignment per materialized session.
  head_coach_id      UUID NOT NULL REFERENCES coaches(id) ON DELETE RESTRICT,
  assistant_coach_id UUID          REFERENCES coaches(id) ON DELETE SET NULL,

  -- Active lifetime of this template.
  starts_on DATE NOT NULL DEFAULT CURRENT_DATE,
  ends_on   DATE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT chk_time_order CHECK (end_time > start_time),
  CONSTRAINT chk_range_valid CHECK (ends_on IS NULL OR ends_on >= starts_on)
);

CREATE INDEX idx_templates_tenant_class ON class_schedule_templates(tenant_id, class_id);
CREATE INDEX idx_templates_active ON class_schedule_templates(tenant_id) WHERE is_active;
```

### `class_sessions` table

```sql
CREATE TABLE class_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id UUID NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,

  -- Back-pointer to the template, NULL for ad-hoc sessions.
  template_id UUID REFERENCES class_schedule_templates(id) ON DELETE SET NULL,

  starts_at TIMESTAMPTZ NOT NULL,
  ends_at   TIMESTAMPTZ NOT NULL,

  head_coach_id      UUID REFERENCES coaches(id) ON DELETE SET NULL,
  assistant_coach_id UUID REFERENCES coaches(id) ON DELETE SET NULL,

  status TEXT NOT NULL DEFAULT 'scheduled'
    CHECK (status IN ('scheduled', 'cancelled')),

  -- Customization tracker: TRUE once the owner edits anything on this
  -- session (cancel, swap coach, shift time). Prevents template
  -- re-materialization from clobbering owner choices.
  is_customized BOOLEAN NOT NULL DEFAULT FALSE,

  cancelled_at     TIMESTAMPTZ,
  cancelled_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  cancellation_reason TEXT,

  notes TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT chk_time_order CHECK (ends_at > starts_at),
  CONSTRAINT chk_cancelled_shape
    CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);

-- Calendar queries: "all sessions in this week."
CREATE INDEX idx_sessions_tenant_range
  ON class_sessions(tenant_id, starts_at)
  WHERE status = 'scheduled';

-- Attribution lookup: "what session is running now for this class?"
CREATE INDEX idx_sessions_class_starts
  ON class_sessions(class_id, starts_at, status);

-- Per-coach weekly view / earnings scan.
CREATE INDEX idx_sessions_head_coach
  ON class_sessions(head_coach_id, starts_at)
  WHERE status = 'scheduled' AND head_coach_id IS NOT NULL;

-- Materialization uniqueness: one session per (template, date+time)
-- so re-materialization is idempotent.
CREATE UNIQUE INDEX ux_sessions_template_starts
  ON class_sessions(template_id, starts_at)
  WHERE template_id IS NOT NULL;
```

### `class_entries.session_id` — new column

```sql
ALTER TABLE class_entries
  ADD COLUMN session_id UUID REFERENCES class_sessions(id) ON DELETE SET NULL;

CREATE INDEX idx_entries_session
  ON class_entries(session_id, entered_at DESC)
  WHERE undone_at IS NULL AND session_id IS NOT NULL;
```

### `tenants.features_enabled` — see `feature-flags.md`

Part of the same migration.

---

## Domain (Layer 3)

### `domain/entities/class_schedule_template.py`

```python
class ClassScheduleTemplate(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    weekdays: list[str]
    start_time: time
    end_time: time
    head_coach_id: UUID
    assistant_coach_id: UUID | None
    starts_on: date
    ends_on: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def covers(self, d: date) -> bool:
        """Does this template apply on the given date?"""
        if d < self.starts_on:
            return False
        if self.ends_on is not None and d > self.ends_on:
            return False
        if not self.is_active:
            return False
        return weekday_code(d) in self.weekdays
```

### `domain/entities/class_session.py`

```python
class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class ClassSession(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    template_id: UUID | None

    starts_at: datetime
    ends_at:   datetime

    head_coach_id:      UUID | None
    assistant_coach_id: UUID | None

    status: SessionStatus
    is_customized: bool

    cancelled_at: datetime | None
    cancelled_by: UUID | None
    cancellation_reason: str | None

    notes: str | None
    created_at: datetime
    updated_at: datetime

    def is_live(self, now: datetime) -> bool:
        """Is this session currently running (useful for check-in)?"""
        return self.status == SessionStatus.SCHEDULED and self.starts_at <= now <= self.ends_at

    def is_completed(self, now: datetime) -> bool:
        return self.status == SessionStatus.SCHEDULED and self.ends_at < now

    def duration_minutes(self) -> int:
        return int((self.ends_at - self.starts_at).total_seconds() / 60)

    def can_cancel(self) -> bool:
        return self.status == SessionStatus.SCHEDULED

    def can_swap_coach(self) -> bool:
        return self.status == SessionStatus.SCHEDULED
```

### Exceptions (added to `domain/exceptions.py`)

- `ClassScheduleTemplateNotFoundError` → 404
- `ClassSessionNotFoundError` → 404
- `SessionStatusTransitionError` → 409 (e.g. cancelling an already-cancelled session)
- `InvalidBulkRangeError` → 422 (from > to, or range > 1 year)
- `FeatureDisabledError("schedule")` → 403 (from `feature_flags.py`)

---

## Materialization logic

Pure helper, unit-testable without a DB:

```python
def materialize_dates(
    template: ClassScheduleTemplate,
    from_: date,
    to: date,
) -> list[date]:
    """Return every date in [from_, to] where the template applies.

    Clipped to template.starts_on / ends_on. Weekday filter applied.
    """
    start = max(from_, template.starts_on)
    end   = to if template.ends_on is None else min(to, template.ends_on)
    out = []
    cursor = start
    while cursor <= end:
        if template.covers(cursor):
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def session_timestamps(
    template: ClassScheduleTemplate,
    session_date: date,
    tenant_tz: ZoneInfo,
) -> tuple[datetime, datetime]:
    """Combine a date + template time + tenant tz → UTC timestamps."""
    naive_start = datetime.combine(session_date, template.start_time)
    naive_end   = datetime.combine(session_date, template.end_time)
    return (
        naive_start.replace(tzinfo=tenant_tz).astimezone(UTC),
        naive_end.replace(tzinfo=tenant_tz).astimezone(UTC),
    )
```

### Materialize flow

```python
async def materialize_template(template_id, horizon_end: date):
    template = get_template(template_id)
    dates = materialize_dates(template, from_=today, to=horizon_end)

    for d in dates:
        starts_at, ends_at = session_timestamps(template, d, tenant_tz)

        # Idempotent via the unique (template_id, starts_at) index.
        try:
            insert_session(
                template_id=template_id,
                starts_at=starts_at, ends_at=ends_at,
                head_coach_id=template.head_coach_id,
                assistant_coach_id=template.assistant_coach_id,
                status='scheduled',
                is_customized=False,
            )
        except IntegrityError:
            # Session already exists for this date — skip silently.
            # (Re-materialization on template edit uses the update path, not insert.)
            continue
```

### Re-materialization on template edit

```python
async def rematerialize_template(template_id):
    template = get_template(template_id)

    # All future non-customized, non-cancelled sessions tied to this template.
    sessions = list_sessions(
        template_id=template_id,
        starts_at_from=now,
        status='scheduled',
        is_customized=False,
    )

    for s in sessions:
        starts_at, ends_at = session_timestamps(template, s.starts_at.date(), tenant_tz)
        update_session(s.id, {
            'starts_at': starts_at,
            'ends_at': ends_at,
            'head_coach_id': template.head_coach_id,
            'assistant_coach_id': template.assistant_coach_id,
        })

    # Then extend the horizon (in case template weekdays changed).
    await materialize_template(template_id, horizon_end)
```

---

## API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/schedule/templates` | owner+ | Create a template. Auto-materializes 8 weeks. |
| GET | `/api/v1/schedule/templates` | Bearer | List templates in caller's tenant. |
| GET | `/api/v1/schedule/templates/{id}` | Bearer | Single template. |
| PATCH | `/api/v1/schedule/templates/{id}` | owner+ | Edit template. Triggers re-materialization of future non-customized sessions. |
| DELETE | `/api/v1/schedule/templates/{id}` | owner+ | Set `is_active=false` + cancel all future non-customized sessions (soft delete). Hard delete blocked while sessions exist. |
| POST | `/api/v1/schedule/sessions` | owner+ | Ad-hoc session (no template). |
| GET | `/api/v1/schedule/sessions` | Bearer | Query by range: `from`, `to`, optional `class_id`, `coach_id`. |
| GET | `/api/v1/schedule/sessions/{id}` | Bearer | Single session. |
| PATCH | `/api/v1/schedule/sessions/{id}` | owner+ | Swap coach / edit time / add notes. Sets `is_customized=TRUE`. |
| POST | `/api/v1/schedule/sessions/{id}/cancel` | owner+ | Cancel one session. Body: `{reason?}`. |
| POST | `/api/v1/schedule/bulk-action` | owner+ | Body: `{class_id, from, to, action: 'cancel'\|'swap_coach', new_coach_id?, reason?}` — applies in one transaction, logs `schedule.bulk_action`. |
| GET | `/api/v1/coaches/{id}/sessions` | owner+ or self | Coach's upcoming sessions (used by the coach-portal view). |

**No PUT / full-replace** — PATCH only. Explicit endpoints for
state transitions so the audit trail is crisp.

**Why no "restore cancelled" endpoint?** Cancellation is terminal;
"undo" = create a fresh session with the same metadata. Keeps
audit clean.

---

## Frontend

### Feature folder

```
features/schedule/
├── api.ts                       # ~12 endpoint wrappers
├── hooks.ts                     # TanStack Query hooks
├── types.ts                     # re-exports from api-types
├── SchedulePage.tsx             # /schedule — week grid
├── WeekGrid.tsx                 # time × day matrix, session cards
├── SessionCard.tsx              # one cell — class name, coach, status
├── SessionDetailPanel.tsx       # right-side edit panel
├── TemplateListPage.tsx         # /schedule/templates
├── TemplateForm.tsx             # shared create/edit
├── AdHocSessionDialog.tsx       # "+ שיעור חד-פעמי"
├── BulkActionDialog.tsx         # "טווח תאריכים" flow
├── CoachSchedulePage.tsx        # simpler read-only view for coach role
└── *.test.tsx
```

### Layout sketch — `/schedule` (week view)

```
┌─ PageHeader: "לוח שיעורים" — Week of Apr 26 – May 2, 2026 ─────────┐
│                                                                     │
│  [← week]  [week 19, 2026]  [week →]       [+ תבנית]  [+ חד-פעמי]  │
│                                             [טווח תאריכים ⋯]         │
└─────────────────────────────────────────────────────────────────────┘

┌─────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ Hr  │ Sun  │ Mon  │ Tue  │ Wed  │ Thu  │ Fri  │ Sat  │
├─────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│ 6   │      │ Yoga │      │ Yoga │      │      │      │
│     │      │ Amir │      │ Amir │      │      │      │
├─────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│ 18  │Boxing│      │Boxing│      │Spin  │      │      │
│     │David │      │  🚫  │      │Noa   │      │      │
└─────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘

Click a cell → slide-in panel:
┌─ Boxing — Sun Apr 26, 18:00 – 19:00 ────┐
│  מאמן ראשי: David Cohen  [החלף]          │
│  מאמן עוזר: (אין)          [+ הוסף]      │
│                                          │
│  [🚫 בטל שיעור]  [ערוך זמן]              │
│                                          │
│  כניסות שנרשמו (מתעדכן בזמן אמת): 0      │
└──────────────────────────────────────────┘
```

- Cells color-coded by class color (reuses `classes.color`).
- Cancelled sessions render with a strikethrough + 🚫 icon.
- Ad-hoc sessions render with a subtle "★" badge.

### Coach role view

- Route: `/schedule` still, but if `user.role === "coach"` the page
  swaps to `CoachSchedulePage` — same week grid, filtered to
  `head_coach_id = self` or `assistant_coach_id = self`.
- Read-only. No edit actions visible.

### Routes + permissions

```tsx
<Route element={<RequireFeature feature="schedule" />}>
  <Route path="/schedule" element={<SchedulePage />} />
  <Route path="/schedule/templates" element={<TemplateListPage />} />
</Route>
```

New `schedule` entry in the `Feature` union. Gated via tenant flag
(`tenant.features_enabled.schedule`) + role baseline.

Permissions:

| Role | Schedule feature |
|---|---|
| owner | Full CRUD |
| super_admin | Platform — doesn't normally edit a tenant's schedule but has access |
| staff | Read-only (to inform check-in) |
| sales | Read-only (context for trial bookings) |
| coach | Read — own sessions only (service-layer filter) |

### Error humanizer

`humanizeScheduleError` in `lib/api-errors.ts`:

- 403 `FEATURE_DISABLED` → "תכונת לוח השיעורים לא זמינה לחדר כושר זה"
- 404 → "השיעור / התבנית לא נמצאו"
- 409 `status_transition` → "לא ניתן לבטל שיעור שכבר בוטל"
- 422 `invalid_bulk_range` → "טווח התאריכים לא תקין"
- 422 → "הפרטים שהוזנו אינם תקינים"

---

## Observability

Structlog events:

| Event | Fields | When |
|---|---|---|
| `schedule.template_created` | tenant_id, template_id, class_id, weekdays | Template create |
| `schedule.template_edited` | tenant_id, template_id, diff | Template PATCH |
| `schedule.template_deactivated` | tenant_id, template_id, sessions_cancelled | Template soft-delete |
| `schedule.session_materialized` | tenant_id, template_id, session_id, starts_at | Every session insert (can be high-volume — sample if needed) |
| `schedule.session_cancelled` | tenant_id, session_id, by, reason | Cancel |
| `schedule.session_coach_swapped` | tenant_id, session_id, old_coach, new_coach, by | Swap |
| `schedule.session_time_edited` | tenant_id, session_id, old_start, new_start, by | Time edit |
| `schedule.session_created_adhoc` | tenant_id, session_id, class_id, coach_id, by | Ad-hoc |
| `schedule.bulk_action` | tenant_id, action, class_id, range, affected_session_ids, by | Bulk range |
| `schedule.horizon_extended` | tenant_id, template_id, sessions_created | Nightly beat job |
| `attendance.coach_attributed` | (existing, `method` field now includes `session`) | Every check-in |

Dashboard widgets / CloudWatch Logs Insights queries (follow-up, the data is already in the logs):

- Calendar density: sessions per tenant per week
- Cancellation rate: cancelled / total
- Swap rate: coach_swapped events / total sessions (high = scheduling problems)
- Drop-in rate: entries with session_id=NULL / total entries

---

## Celery beat job

`app/worker/tasks/schedule_horizon.py`

```python
@celery_app.task(name="schedule.extend_horizon")
def extend_schedule_horizon():
    """Nightly: for every active template, ensure ~8 weeks of future sessions."""
    with sync_session() as s:
        templates = active_templates(s)
        for t in templates:
            latest = latest_materialized_date(s, t.id)
            if latest is None or (latest - today()).days < 42:  # <6 weeks left
                materialize_template(s, t, horizon_end=today() + timedelta(weeks=8))

    log.info("schedule.horizon_extended", templates_processed=len(templates))


# celery_beat_schedule.py
beat_schedule = {
    'schedule-extend-horizon': {
        'task': 'schedule.extend_horizon',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

**Retry behavior:** task is idempotent (unique index on
`(template_id, starts_at)`). Failed runs just re-execute next night.

---

## Tests

### Backend

| Type | File | Coverage |
|---|---|---|
| Unit | `test_class_schedule_template_entity.py` | `covers(date)` weekday math, active/inactive, range checks |
| Unit | `test_class_session_entity.py` | `is_live`, `is_completed`, `duration_minutes`, `can_cancel` |
| Unit | `test_materialize.py` | `materialize_dates` — every weekday, range clipping, DST transition, leap day; `session_timestamps` UTC conversion |
| Unit | `test_feature_flags.py` | gated / ungated / unknown-feature |
| Integration | `test_schedule_template_repo.py` | CRUD, cross-tenant isolation, active filter |
| Integration | `test_class_session_repo.py` | CRUD, range queries, unique index rejects dup materialization, status transitions |
| Integration | `test_rematerialize.py` | Edit template → future non-customized sessions shift; customized + cancelled stay; new weekday adds sessions, removed weekday deletes unmaterialized/future non-customized |
| E2E | `test_schedule.py` | Create template → 8 weeks of sessions appear; cancel one → status=cancelled + pay=0; swap coach → logged; ad-hoc; bulk cancel range; bulk swap range; feature off → 403 on every endpoint |
| E2E | `test_schedule_attendance_attribution.py` | Entry during scheduled window → `session_id` set + `coach_id=session.head_coach_id`; entry outside any session → `session_id=NULL` + weekday fallback; cancelled session + entry → no attribution |
| E2E | `test_cross_tenant_isolation.py` (+additions) | ~15 probes for every new endpoint |
| E2E | `test_tenant_features.py` | super_admin toggles, owner gets 403 on PATCH /features |

Target: **~45 new backend tests**.

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | All endpoints (URL + body shape) |
| `WeekGrid.test.tsx` | 7 day columns + 24 hour rows, click dispatches to parent |
| `SessionCard.test.tsx` | Renders status, color, coach name; cancelled style |
| `SessionDetailPanel.test.tsx` | Edit form wired, cancel opens ConfirmDialog |
| `TemplateForm.test.tsx` | Weekdays picker + time pickers + coach combobox |
| `BulkActionDialog.test.tsx` | Date range picker + action select + coach combobox (when swap) |
| `CoachSchedulePage.test.tsx` | Read-only — no edit buttons |
| `SchedulePage.test.tsx` | Week navigation, feature-flag-off state shows nothing |
| `permissions.test.ts` (+additions) | coach feature + gated tenant logic |

Target: **~30 new frontend tests**.

### Load test

`loadtests/test_schedule_load.py`:

- `ScheduleBrowser` VU — polls `/schedule/sessions?from=..&to=..` every 10s (mimics owner watching the week view).
- `StaffCheckin` VU — mixes `quota_check` + `attendance` record with session-based attribution hitting the `idx_sessions_class_starts` index.
- Targets:
  - 99p `/schedule/sessions` < 100ms at 10 VU.
  - 99p `/attendance` (with session lookup) < 120ms at 10 VU (vs. 100ms baseline — the extra session lookup costs ~20ms).

---

## V1 → future migration path

Nothing in v1 boxes in v2. Evolution notes:

- **Coach self-service** — the coach role already has read access to
  their sessions. Adding `POST /schedule/sessions/{id}/request-swap`
  + a notification surface is additive.
- **Member-facing schedule** — the data model supports a public read
  (no auth, or member-scoped), just needs a UI + a rate-limited
  endpoint.
- **Waitlists** — new `class_session_reservations` table, references
  `class_sessions`. Capacity limits as a `max_capacity INTEGER` column
  on `class_sessions`.
- **Google Calendar / iCal** — read sessions, emit an ICS stream at
  `GET /schedule/export.ics`. Needs auth token scheme (URL-based
  secret token per user). Future.
- **Schedule templates with exceptions** — Google Calendar-style
  "cancel every Tuesday for 4 weeks" = the bulk action already
  handles this. If owners want a persistent "recurring exception"
  pattern, add a `class_schedule_exceptions` table later.

---

## Open questions (to revisit during implementation)

1. **Materialization on template create** — should the first session
   appear today (if today matches the template's weekday) or only
   starting tomorrow? Leaning toward **today** — if owner creates
   "boxing Sun+Tue" on a Sunday morning, they probably want today's
   session to appear.
2. **Drop-in grace period** — 30 minutes as the attribution tolerance.
   Too generous? Too tight? Gym-dependent. Could move to
   `tenants.feature_configs` later if it becomes a per-gym knob.
3. **Timezone** — hardcoded `Asia/Jerusalem` in this spec. When we
   onboard a non-IL gym, migrate to `tenants.timezone`. Single helper
   that reads from tenant so the change is a one-liner.
4. **Per-session assistant pay** — today only `head_coach_id` gets
   `per_session` / `per_attendance` credit. The `assistant_coach_id`
   is informational. Pay for assistants follows their `class_coaches`
   link (`pay_model=fixed` is the most common for assistants). If a
   real gym wants per-session assistant pay, separate `class_coaches`
   rows for the assistant role already cover it via the existing
   earnings path.
5. **Auto-cancellation of past scheduled sessions with zero entries** —
   a session that ended with no check-ins is almost certainly a
   "ghost" the owner forgot to cancel. Do nothing automated for now;
   payroll counts it as scheduled; owner cancels manually to zero out
   pay. Could add an owner-facing "cleanup ghost sessions" helper
   later.

---

## Migration plan

Single combined PR — backend + frontend + feature-flag mechanism.
Estimate: **3 days** (larger than Coaches because of the week-view UI
+ beat job + bulk action).

**Backend:**

1. Migration 0012: `class_schedule_templates`, `class_sessions`,
   `class_entries.session_id`, `tenants.features_enabled` + backfill.
2. `app/core/feature_flags.py` + `FeatureDisabledError` + error_handler.
3. Domain entities + exceptions + unit tests.
4. Repos (template, session, extended entry repo for session-scoped queries).
5. `ScheduleService` — CRUD, materialization, re-materialization, bulk action.
6. `AttendanceService.record_entry` — add session-lookup branch ahead of weekday fallback.
7. `CoachService.earnings_for` — branch on feature flag, session-based
   pay for `per_session` model when Schedule is on.
8. `PATCH /tenants/{id}/features` endpoint for super_admin.
9. Routes + schemas.
10. Celery beat task for horizon extension.
11. E2E tests (including feature-flag isolation probes).
12. Backfill considerations: existing `class_entries` rows stay
    `session_id=NULL` — no retroactive attribution. New entries start
    picking up session_id once templates exist.

**Frontend:**

1. Feature folder with pages/components.
2. `canAccess` update + `tenantFeatures` threaded through auth-provider.
3. Sidebar + route guards.
4. `humanizeScheduleError`.
5. Tenant detail page gains a "Features" section for super_admin.
6. Tests.

**Docs / spec:**

1. `docs/spec.md` §3.11 Schedule + §3.12 Feature Flags.
2. `docs/crm_logic.md` — new session-based attribution section,
   updated per_session pay math, feature-flag permission layer.
3. `docs/features/schedule.md` — this doc, authoritative.
4. `docs/features/feature-flags.md` — companion doc.

---

## Related docs

- [`spec.md`](../spec.md) — product-level overview, roadmap
- [`crm_logic.md`](../crm_logic.md) — cross-feature business rules
  (attribution, pay models, state machines, permission layering)
- [`feature-flags.md`](./feature-flags.md) — the tenant-level gating
  mechanism that ships alongside Schedule
- [`coaches.md`](./coaches.md) — coach entity + `class_coaches` link +
  weekday-pattern attribution (the fallback when Schedule is off or
  no session matches)
- [`attendance.md`](./attendance.md) — check-in flow that picks up
  `class_entries.session_id`
- [`classes.md`](./classes.md) — class catalog that sessions reference
