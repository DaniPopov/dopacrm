# Feature: Attendance (Check-in / Entrance)

> **Status:** Planned. Not yet implemented. Plan for review.
>
> **Order:** Build AFTER Subscriptions (shipped). BEFORE Payments is OK
> — they're independent. Attendance validates the entitlement model
> end-to-end; if the quota math is wrong, this is where we find out.
>
> **What this is:** the front-desk "check-in" flow. Staff picks a member,
> sees their current subscription + available class quotas, taps a class
> to record an entry. Quota counters tick down. Includes undo for mistakes.

---

## Summary

Attendance is the feature that **finally validates whether our Plans +
Subscriptions + Entitlements data model actually works**. Everything we
built for Plans — the entitlement rows with `quantity`, `reset_period`,
`class_id` — was designed to be *consumed* at check-in time. Until
something consumes them, they're just data sitting in a table.

Specifically, this feature builds:

- **A `/check-in` front-desk page** — staff picks a member, sees their
  sub + current quota usage, taps a class to record the entry.
- **A `class_entries` table** — one row per entry, FK to member + sub +
  class, with an `undone_at` column instead of a hard delete.
- **Quota enforcement** — an entry is allowed only if the member's
  subscription has an entitlement that covers this class AND the current
  reset-period window still has quota remaining.
- **Undo** — staff can reverse a mistaken check-in within a configurable
  window (default: 24 hours). Undoing returns the quota.
- **Member self-view** (future) — "how many classes do I have left?"
  becomes a real query. Ships as a read-only endpoint here; the self-
  service portal is a later phase.

---

## Why it's a separate feature (not folded into Members or Subscriptions)

- **Different write frequency.** A member has ~1 write per week (subscription
  changes). An entry happens every time they walk through the door — 3–5
  per week per active member. The volume is an order of magnitude higher;
  mixing high-frequency writes into the subscription lifecycle table
  pollutes query performance for everything else.
- **Different query patterns.** "What classes did Dana do this month?"
  is a range query by `member_id + entered_at`. "Which members came
  today?" is `tenant_id + entered_at::date = today`. Both want their own
  indexes, separate from the subscription shape.
- **Different lifecycle semantics.** Entries are append-only with a
  cheap undo. Subscriptions have a 5-state machine. Coupling them would
  force the attendance table into the subscription's shape CHECKs.
- **Different permission gate.** Any staff can record a check-in — this
  is the highest-frequency action they perform. Subscription mutations
  are also staff+, but the UI surface is different (a simple tap button
  vs. a form).

---

## Where this sits in Phase 2 / 3

```
  Phase 2 (Core CRM) — shipped:
    Members / Classes / Membership Plans / Subscriptions
    Payments (not yet)

  Phase 3 (Operations):
    Attendance             ← THIS DOC
    Class schedule / sessions (future — "when is spinning on Monday?")
    Staff shifts / leads (future)
```

Attendance is at the **boundary** of Phase 2 and 3. It's tightly
coupled to subscription entitlements (Phase 2), but it's also the first
"daily-ops" feature (Phase 3). We ship it now because:

1. It closes the loop on our Plans design. If we got entitlements wrong,
   this is where it surfaces.
2. The gym owner can't demo DopaCRM to real staff without a check-in
   workflow — every existing competitor has one, and the gap is
   immediately obvious.
3. Payments is independent; we can build them in either order.

---

## User stories

1. **As front-desk staff**, I open `/check-in` and pick a member — either
   by **scanning their QR code** (the member's ID encoded, shown on their
   phone or printed card) OR by typing their name/phone. I see their
   active subscription + remaining quota per class this week / month. I
   tap a class → the entry is recorded, the quota ticks down.
2. **As staff**, if the member has no active subscription, I see a clear
   "no active subscription" message with a link to enroll. No check-in
   is recorded.
3. **As staff**, if the member is at quota (e.g., 3/3 for the week), I
   see a warning + an "override" button. Owner-configurable whether
   staff can override, or only the owner — see decision #1 below.
4. **As staff**, if I recorded a wrong entry, I tap "undo" within 24
   hours and the entry is reversed. The quota returns.
5. **As the owner**, I see today's attendance at a glance on the
   dashboard ("37 members checked in today"). Trending over a week/month
   becomes a chart.
6. **As a member** (future self-service), I see my remaining classes for
   the week on my personal page.

**Explicitly NOT in this feature:**
- Class scheduling ("yoga is on Monday at 18:00") — needs its own model;
  lands as `class_sessions` in Phase 3.
- Attendance reporting dashboard beyond the "today" count — the raw data
  is there; full reports are a separate milestone.
- Paid drop-ins without a subscription — staff records a one-time entry
  AND a payment. This needs Payments first. For v1, drop-ins require a
  one-time subscription (which is already supported via `PlanType.ONE_TIME`).
- Geofencing / member self-service check-in — always a STAFF action in
  v1. The member shows a QR, staff scans it — staff is in the loop.
- QR revocation / token rotation — v1 encodes `member.id` directly.
  Future: add a random `qr_token` column + regenerate endpoint.

---

## Decisions (with the 5 open-question answers baked in)

### 1. Quota enforcement — warn + override, NOT hard-block

Real gyms are messier than the data model. A member might show up
outside their usual pattern, a staff member might want to grant a
courtesy entry, a birthday class is on the house. Hard-blocking creates
customer-service friction.

**Proposed v1:**
- At-quota state shows a warning modal: "Dana has used 3/3 of her weekly
  group classes. Allow entry anyway?"
- Staff can override. The override is logged in the event data
  (`event_data.override=true`, `override_reason?`).
- The class entry still counts against the member's usage for reporting,
  but doesn't prevent the entry.

**Owner-configurable later:** per-tenant setting `require_owner_override`
to gate who can click the override button. v1 default: any staff can
override. Phase 4 makes this configurable.

### 2. Undo window — 24 hours, soft-delete, OWNER-AUDITABLE

Entries are soft-deleted via `undone_at` + `undone_by` + `undone_reason`.
The row stays in the DB so reporting stays honest ("it was a mistake,
not a real entry"). Quota counting queries filter out `undone_at IS NOT NULL`.

**Why 24 hours specifically?** Long enough that staff who realize the
mistake the next shift can still fix it. Short enough that stale entries
don't get "cleaned up" months later with no context.

**Who can undo?** The staff member who created the entry OR owner.

**After 24h:** undo disappears from the UI. If a correction is needed
past the window, owner makes a corrective entry (future audit log).
v1: just don't allow past the window.

**Owner audit trail — by design, not afterthought:**
- Every undo emits a `structlog` event with
  `{event: "attendance.undo", tenant_id, entry_id, undone_by,
  hours_since_entry, reason}`. Surfaced via CloudWatch Logs Insights / Sentry for owner audit.
- List endpoint supports `include_undone=true&undone_by_staff=true` for
  the owner's "mistakes this week" view.
- Dashboard widget (future milestone): "5 entries undone by staff this
  week (3 by Amir, 2 by Noa)". Fraud-detection + coaching signal. The
  raw data is there; the widget is a follow-up.

Same discipline for **overrides** (quota exceeded / not-covered): every
override writes `override=true` + optional reason AND a structlog event.
Patterns show up — "staff X overrode 40× last month" is either training
or abuse.

### 3. Drop-ins / trial — require a sub (even if it's a one-time plan)

Short answer: **every class entry references a subscription.** Even a
one-time "free trial class" is a one-time subscription with
`price_cents=0, duration_days=1`. This keeps the attendance model
consistent: every entry FKs to exactly one sub.

**Why not allow subscriptionless entries?**
- Complicates every report ("how many entries last month per plan?" now
  needs to bucket null plan_ids).
- Masks the data: "We have 40 check-ins but only 25 subscribed members"
  → owner has no paper trail of who those 15 were or why they got in.
- Breaks the entitlement model — without a sub, there's no quota to
  check against.

**When Payments lands:** the drop-in flow becomes a single staff action
that creates a one-time sub + records a payment + records the entry —
but the underlying model stays the same.

### 4. Which class the entry counts against — staff picks

Staff picks from the list of classes the member's plan covers.
Specifically: classes where the member's active sub has an entitlement
that matches (or an unlimited-any-class entitlement).

**UX:**
- Member has 3/week group + 1/week PT entitlements.
- The check-in page shows ALL classes the tenant offers, but grays out
  classes that aren't covered. Covered classes show the remaining quota
  ("Yoga — 2 left this week").
- Tapping a grayed-out class asks "This class isn't in the member's
  plan. Allow as override?" → same override modal as at-quota.

**Why not auto-pick?** A member can attend different classes in the
same week (yoga Monday, spin Wednesday). Each entry has to explicitly
reference ONE class. Staff is the best judge.

### 5.5 Member QR code — member.id encoded, no storage

Every member effectively has a QR code. Implementation: the member detail
page has a "הצג QR / הדפס כרטיס" button that renders a QR encoding the
member's UUID client-side via the `qrcode` npm lib. No migration, no
stored blob, no image hosting — the UUID is enough.

**Check-in page supports two input modes:**
- **Scan** — a "סרוק" button opens the device camera. A decoded UUID
  gets passed through the exact same `/quota-check` + `/attendance`
  flow as a manual pick. Uses `@zxing/browser` (lightweight, no server).
- **Search** — the existing name/phone text box. Unchanged.

**Security posture:** the QR encodes the member UUID, not a secret. If
the QR leaks, a stranger could scan it at this gym — but staff is in
the loop (the "member" has to physically walk up + get the check-in).
Same risk model as a physical membership card, which gyms have been
living with for decades. Not a v1 concern.

**Cross-tenant isolation is free:** scanning a member-UUID from gym A
at gym B hits `GET /members/{uuid}` in gym B's scope → 404. No tenant
leak possible.

**Future (deferred until a gym asks):**
- `members.qr_token` column, random, rotateable.
- `POST /api/v1/members/{id}/regenerate-qr` to invalidate the old QR.
- QR payload switches from member.id to the token.

### 6. Entry timestamp — always `now`, no backdating in v1

Recording an entry uses the server's current time. Staff cannot pick a
date.

**Why no backdating?**
- Every gym I've seen abuses backdating ("she really came yesterday,
  I just forgot to check her in"). That's a policy problem, not a
  tool problem — tools shouldn't enable it.
- Makes the "check-in count today" query a trivial `entered_at::date =
  today` without quality-of-data caveats.
- If a legitimate correction is needed, the **undo** flow handles the
  "recorded wrong class" case; an "I forgot yesterday" case is rare
  enough that v1 ignoring it is fine.

If real gyms ask for this later, add a `recorded_backdated=true` flag
with explicit owner approval. Not before.

---

## Data Model

**`class_entries` table** (migration `0010_create_class_entries.py`)

```sql
CREATE TABLE class_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
  subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
  class_id UUID NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,

  entered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  entered_by UUID REFERENCES users(id) ON DELETE SET NULL,

  -- Soft-delete / undo
  undone_at TIMESTAMPTZ,
  undone_by UUID REFERENCES users(id) ON DELETE SET NULL,
  undone_reason TEXT,

  -- Override telemetry (staff bypassed a quota or a non-covered class)
  override BOOLEAN NOT NULL DEFAULT false,
  override_reason TEXT
);

-- Hot paths
CREATE INDEX idx_entries_tenant_day
  ON class_entries (tenant_id, (entered_at::date) DESC);
CREATE INDEX idx_entries_member_recent
  ON class_entries (member_id, entered_at DESC);
CREATE INDEX idx_entries_subscription
  ON class_entries (subscription_id, entered_at DESC);

-- "Effective" entries (exclude soft-deleted) — used by every quota query.
-- Partial index keeps the quota-check hot path small.
CREATE INDEX idx_entries_effective
  ON class_entries (member_id, class_id, entered_at)
  WHERE undone_at IS NULL;
```

**Design choices:**

- **`entered_at` is a TIMESTAMPTZ** (not DATE) — we need hour-level
  precision for "who came at 06:00 today" and for the 24h undo window
  calculation.
- **Soft-delete via `undone_at`** (NOT a status enum) because an entry
  has exactly two states: recorded or undone. No multi-state machine
  needed, and reporting queries love `WHERE undone_at IS NULL`.
- **`ON DELETE RESTRICT`** on member/sub/class — same rule as everywhere:
  we don't hard-delete things that have history.
- **Partial index on effective entries** — quota queries always filter
  out undone rows; the partial index is much smaller than a full index.
- **`override BOOLEAN` + `override_reason`** — dashboards can filter on
  this to spot unusual patterns. "Last month 42 entries were overrides
  by staff X" — either training issue or data-entry fraud.
- **No `class_entry_events` log table** (unlike subscriptions). The row
  itself has `entered_by` + `undone_by` + `undone_reason`, which is
  the full state machine. Two states = no need for a separate log.

---

## Domain (Layer 3)

**`domain/entities/class_entry.py`**

```python
class ClassEntry(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    subscription_id: UUID
    class_id: UUID

    entered_at: datetime
    entered_by: UUID | None

    undone_at: datetime | None
    undone_by: UUID | None
    undone_reason: str | None

    override: bool
    override_reason: str | None

    def is_effective(self) -> bool:
        """True if this entry counts toward usage (not undone)."""
        return self.undone_at is None

    def can_undo(self, by_user_id: UUID, now: datetime) -> bool:
        """Undo window: 24h from entered_at, restricted to the creator
        or owner (enforced in service). Service caller provides current
        time for testability."""
        if self.undone_at is not None:
            return False  # already undone
        age = now - self.entered_at
        return age <= timedelta(hours=24)
```

**Exceptions** (added to `domain/exceptions.py`):
- `ClassEntryNotFoundError` → 404
- `MemberHasNoActiveSubscriptionError` → 409 ("enroll them first")
- `QuotaExceededError` → 409 (with details; UI shows the override modal)
- `ClassNotCoveredByPlanError` → 409 (same — UI shows override)
- `UndoWindowExpiredError` → 409
- `ClassEntryAlreadyUndoneError` → 409

---

## Quota-check logic (the interesting part)

The service's `record_entry` method is the test of whether the Plans
entitlement model actually works. Pseudocode:

```python
def check_quota(member_id, class_id, now) -> QuotaCheckResult:
    sub = find_current_subscription(member_id)            # 404 if none
    if not sub.is_live(): raise MemberHasNoActiveSubError

    entitlements = sub.plan.entitlements                  # eager-loaded

    # Find the matching entitlement (exact class > any-class wildcard)
    match = find_matching_entitlement(entitlements, class_id)
    if match is None:
        return QuotaCheckResult(allowed=False, reason="not_covered")

    if match.reset_period == UNLIMITED:
        return QuotaCheckResult(allowed=True)

    # Count effective entries in the current reset window
    window_start = compute_window_start(match.reset_period, now, sub.started_at)
    used = count_entries(
        member_id=member_id,
        class_id=class_id if match.class_id else None,    # any-class → count all
        since=window_start,
        effective_only=True,
    )

    remaining = match.quantity - used
    if remaining <= 0:
        return QuotaCheckResult(allowed=False, reason="quota_exceeded", used=used)
    return QuotaCheckResult(allowed=True, remaining=remaining)
```

**Matching entitlement precedence:** exact-class match wins over
any-class wildcard. If a plan has "3 yoga/week + unlimited any-class",
a yoga entry counts against the 3/week limit; a spinning entry hits the
unlimited rule.

**Reset-window boundaries** depend on the reset_period:
- `WEEKLY` — Sunday 00:00 local (Israel). Rolling weeks, not ISO weeks.
- `MONTHLY` — 1st of the month 00:00.
- `BILLING_PERIOD` — from `subscription.started_at` + N * billing_period_days.
- `NEVER` — since `subscription.started_at` (total-across-sub).
- `UNLIMITED` — no window.

---

## API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/attendance/quota-check` | staff+ | Query params: `member_id`, `class_id`. Returns the quota result (used for UI to gray out / show "2 left" / show warning). Doesn't record anything. |
| POST | `/api/v1/attendance` | staff+ | Record an entry. Body: `{member_id, class_id, override?, override_reason?}`. Server computes quota + records the entry atomically. |
| POST | `/api/v1/attendance/{id}/undo` | staff+ | Undo within 24h. Body: `{reason?}`. |
| GET | `/api/v1/attendance` | Bearer | List recent entries for the tenant. Filter by `member_id`, `class_id`, `date_from` / `date_to`. |
| GET | `/api/v1/members/{id}/attendance` | Bearer | All entries for one member (shown on member detail page). |
| GET | `/api/v1/members/{id}/attendance/summary` | Bearer | Compact: "used 2/3 of group-class weekly quota, unlimited PT". Used by the check-in page header. |

**Why no PATCH?** Entries are append-only. Corrections = undo + re-record. Audit trail stays honest.

**Why no DELETE?** Undo IS the soft-delete. Never hard-delete.

---

## Frontend

### Feature folder

```
features/attendance/
├── api.ts                     # 6 functions
├── hooks.ts                   # TanStack Query wrappers
├── types.ts                   # re-exports from api-types
├── CheckInPage.tsx            # /check-in — the staff workflow
├── MemberPicker.tsx           # dual-mode: QR scan OR name/phone search
├── QrScannerPanel.tsx         # camera-based UUID scan (@zxing/browser)
├── ClassGrid.tsx              # grid of classes with quota badges
├── QuotaOverrideDialog.tsx    # "at quota / not covered → allow anyway?"
├── RecentEntriesFeed.tsx      # "Dana — Yoga — 2 min ago" with undo
└── *.test.tsx
```

Additional: the existing **Member detail page** gains a "הצג QR / הדפס
כרטיס" button (via the `qrcode` npm lib, renders client-side). Prints
a A6 card layout with the gym logo + member name + QR encoding
`member.id`.

### Layout

```
/check-in
┌── Pick member ─────────────────────────────────────┐
│  [📷 סרוק QR]  או  🔍 [חיפוש לפי שם/טלפון...]      │
│  recent: [Dana C.] [Amir L.] [Noa M.]              │
└────────────────────────────────────────────────────┘

Once a member is picked:

┌── דנה כהן — מנוי פעיל ─────────────────────────────┐
│  מסלול: חודשי — 3 קבוצתי + 1 PT                   │
│  תוקף: 1 במאי 2026                                  │
│  יתרה השבוע: 2/3 קבוצתי, 1/1 PT                    │
└────────────────────────────────────────────────────┘

┌── בחר שיעור ───────────────────────────────────────┐
│  ┌─ יוגה ──┐ ┌─ ספינינג ──┐ ┌─ PT ──────┐          │
│  │  ✓ 2    │ │   ✓ 2     │ │  ✓ 1     │          │
│  │  נותרו  │ │   נותרו   │ │  נותר    │          │
│  └─────────┘ └───────────┘ └──────────┘          │
│  ┌─ קרוספיט ┐ ┌─ פילאטיס ─┐                       │
│  │  לא     │ │   לא      │   (grayed — not covered)
│  │  בתוכנית│ │   בתוכנית │                       │
│  └─────────┘ └───────────┘                       │
└────────────────────────────────────────────────────┘

┌── כניסות אחרונות (undo) ──────────────────────────┐
│  Dana Cohen — יוגה — לפני 2 דקות  [בטל]           │
│  Amir Levy — ספינינג — לפני 15 דקות  [בטל]        │
│  Noa M. — PT — לפני שעה            [בטל]           │
│  ...                                               │
└────────────────────────────────────────────────────┘
```

Tapping a class card triggers one of:
- **Covered + quota remaining** → immediate entry record, optimistic UI.
- **Covered + at quota** → QuotaOverrideDialog (warning + Override button).
- **Not covered** → QuotaOverrideDialog (same, different wording).

The "recent entries" strip lives below the class grid, shows everyone
(not just the currently selected member) so staff can undo any recent
mistake across members.

### Routes + permissions

- `/check-in` — new top-level route. `feature: "attendance"` added to
  `permissions.ts`. Baseline: staff, owner, super_admin (super_admin
  reads only — they can't record for a gym).
- Sidebar: new entry "כניסות" (attendance) with a door icon. Goes RIGHT
  after "מנויים" since it's daily front-desk ops.

### Error humanizer

`humanizeAttendanceError` in `lib/api-errors.ts`:
- 404 → "הפריט לא נמצא"
- 409 `no_active_subscription` → "למנוי זה אין מנוי פעיל. יש להרשום תחילה"
- 409 `quota_exceeded` → "המנוי מיצה את המכסה לתקופה" (but UI handles this via the override modal, not a toast)
- 409 `not_covered` → "השיעור לא כלול במסלול"
- 409 `undo_window_expired` → "חלון הביטול (24 שעות) פג"

---

## Observability (first-class, not afterthought)

Attendance is the **highest-frequency write** in the CRM — every active
member hits it 3–5 times a week. If the quota math is wrong or a slow
query sneaks in, it'll be the first place we feel it.

**Structured log events** (structlog JSON → stdout → CloudWatch Logs in prod):

| Event | Fields | When |
|---|---|---|
| `attendance.recorded` | tenant_id, member_id, class_id, subscription_id, entered_by, override, quota_remaining | Every entry inserted |
| `attendance.override` | tenant_id, member_id, class_id, staff_id, reason, kind ("quota_exceeded" / "not_covered") | Every override (subset of `recorded`) |
| `attendance.undone` | tenant_id, entry_id, undone_by, hours_since_entry, reason | Every undo |
| `attendance.quota_check` | tenant_id, member_id, class_id, allowed, reason | Every quota check (sampled — high volume) |

**Metrics** (optional in v1, written in the code even if dashboard is
later):

- Counter: `attendance_entries_total{tenant, result}` (result = allowed / override / blocked)
- Counter: `attendance_undos_total{tenant, within_window}`
- Histogram: `attendance_quota_check_duration_ms{tenant}` — watch the 99p.

**Dashboard widgets** (future product feature, unblocked by these events):

- "Today's check-ins" — count of `attendance.recorded` events in the last 24h.
- "Undo rate" — `undones / recorded * 100%` — expect < 2%. Spike = training issue.
- "Override rate" — `overrides / recorded * 100%` — per-staff breakdown.

**Sentry:** quota-check exceptions and FK violations already surface via
the global AppError handler. Nothing new needed.

---

## Load testing

Attendance is the only feature where real performance matters. Expected
peak at a mid-sized gym: **200–300 check-ins in a 2-hour evening rush**
(~2–3 QPS on `/quota-check` + `/attendance`). Trivial for Postgres, but
the quota-math query is non-trivial (counts over a rolling reset window
with partial-index filter), so we verify.

`loadtests/test_attendance_load.py` (Locust):

- `GymFrontDesk` virtual user = one staff terminal.
- Tasks (weighted):
  - `quota_check` ×10 — hits every time a member is picked.
  - `record_entry` ×6 — actual check-ins.
  - `list_recent` ×3 — the undo feed refresh.
  - `undo` ×1 — a staff mistake occasionally.
- Mixed member pool (100 pre-seeded members, each with a sub and some
  prior entries) so the quota-math table isn't empty.

Targets:
- 99p `/quota-check` < 50ms at 10 VU.
- 99p `/attendance` (record) < 100ms at 10 VU.
- Zero errors at 20 VU for 60 seconds (stress — what a midsize gym peak
  actually looks like).

Wired into `make load-test-attendance`.

---

## Tests

### Backend

| Type | File | Coverage target |
|---|---|---|
| Unit | `test_class_entry_entity.py` | `is_effective()`, `can_undo()` (edge cases: exactly 24h, already-undone, fresh) |
| Unit | `test_quota_check.py` | Reset-window math for each reset_period, exact-class vs any-class precedence, quota arithmetic |
| Integration | `test_class_entry_repo.py` | CRUD, partial-index filtering of effective entries, cross-tenant isolation |
| E2E | `test_attendance.py` | Happy path (record → undo), quota enforcement, override flow, non-covered class, no-sub 409, undo window expired, scan-by-uuid path (POST with a member id from a "scanned" QR), observability (structlog events fire) |

Target: ~30 new backend tests.

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | 6 endpoints — URL/body shape |
| `CheckInPage.test.tsx` | Member search, QR scan result → member picked, class grid renders with quota badges, click → record, at-quota → modal, not-covered → modal |
| `MemberPicker.test.tsx` | Toggle between scan + search; recent picks list |
| `QrScannerPanel.test.tsx` | Decode callback invoked with UUID (via mocked zxing); error states (camera denied, invalid QR) |
| `QuotaOverrideDialog.test.tsx` | Warning vs. not-covered copy, override reason optional, submit shape |
| `RecentEntriesFeed.test.tsx` | Renders undo button in-window, hides past 24h, click → undo |
| `MemberQrButton.test.tsx` | Renders QR encoding member.id, print action wired |

Target: ~25 new frontend tests.

### Load test

`loadtests/test_attendance_load.py` — see the Load testing section above.
Wired as `make load-test-attendance`.

---

## Open questions (smaller this time)

Material ones all resolved in the Decisions section. Remaining
implementation-time calls:

1. **Timezone for reset windows.** We said "Sunday 00:00 local Israel"
   for the weekly reset. But `entered_at` is stored as UTC. Service
   computes window boundaries by converting to Asia/Jerusalem. Add a
   per-tenant timezone column later if we onboard gyms outside IL.
2. **Member `current_subscription` on `/members/{id}`.** The Subscriptions
   spec left this as "TODO: return nested". The CheckInPage needs it
   returned nested to avoid 3 queries per member pick. Fix as part of
   this work or separately — either way it's small.
3. **Quota-summary caching.** `GET /members/{id}/attendance/summary`
   might get hit 5+ times per member pick. Cheap enough to compute
   fresh (single COUNT per entitlement, 5 entries max per plan). Revisit
   if it shows up in profiling.

---

## Migration plan

Single combined PR — backend + frontend — following the same pattern we
used for Subscriptions. Estimate: ~1.5 days given the quota math + the
interactive check-in page.

**Backend:**
1. Migration `0010_create_class_entries.py` — table + partial indexes.
2. Domain entity + exceptions + unit tests.
3. Repository (with a dedicated quota-check method).
4. `AttendanceService` — record, undo, quota_check, list, list_for_member, summary.
5. Routes + schemas (6 endpoints).
6. Member API: return nested `current_subscription` so the frontend
   doesn't need 3 round-trips per pick.
7. E2E tests.

**Frontend:**
1. Feature folder with the 4 pages/components above.
2. Sidebar + route wiring + `canAccess("attendance")`.
3. `humanizeAttendanceError`.
4. Tests.

---

## Related docs

- [`spec.md`](../spec.md) §3 — Attendance is where the entitlement model
  from §3.5 + §3.6 meets reality.
- [`membership-plans.md`](./membership-plans.md) — source of truth for
  entitlement shape. Attendance consumes these rows.
- [`subscriptions.md`](./subscriptions.md) — sub state machine + price
  lock. Every entry FKs into a live sub.
- [`classes.md`](./classes.md) — what an entry references.
