# Feature: Classes, Class Passes & Attendance

> **Status:** Planned. Not yet implemented. Plan for review.
>
> **Order:** Build AFTER Members. This feature depends on `members.id`.
>
> This is one combined doc covering three closely-coupled tables that ship together:
> 1. `classes` — what the gym offers
> 2. `class_passes` — what a member bought
> 3. `attendance` — when a member used a pass
>
> They could be split, but the data only makes sense together.

---

## Summary

A gym offers **classes** (Spinning, Pilates, CrossFit, Yoga). A member buys a **class pass** for a specific class — either a punch card (10 entries) or unlimited (monthly). When the member shows up, the front desk records **attendance**, which decrements the punch card or just logs it for unlimited passes.

This unlocks the dashboard queries the owner actually cares about:
- "How many members have fewer than 5 entries left for Spinning?"
- "Class utilization this month: 80% for Yoga, 30% for Pilates"
- "Revenue per class type"
- "Which members haven't shown up in 30 days?" (churn signal)

### Where this fits

```
Tenant (gym)
  └── Members (customers)
        └── Class passes (what they bought)
              └── Attendance (when they used it)
        ↑
        Classes (what the gym offers)
```

### What this feature does NOT do (separate features)

- **Class scheduling / calendar** — "Spinning Mondays at 7am" — separate `class_sessions` table later
- **Trainer assignment** — a trainer leads which class — separate when trainers exist
- **Booking / reservations** — member books a slot ahead — separate, depends on scheduling
- **Payment processing** — the `price_cents` on a pass records what was paid; the actual payment record lives in the Payments feature

This feature is the **minimum to track passes and check-ins**. Scheduling and bookings are a much larger feature for v3.

---

## User stories

1. **As an owner**, I create the class types my gym offers (Spinning, Pilates, etc.) — once, on setup.
2. **As an owner**, I edit a class name or color, or deactivate one I no longer offer.
3. **As staff**, I sell a member a class pass — pick member + class + type (punch card / unlimited) + entries (if punch card) + price + expiry.
4. **As staff**, when a member walks in, I record their attendance — pick member + class. Backend auto-decrements their pass.
5. **As staff**, I see all of a member's active passes on their profile.
6. **As an owner**, I see a dashboard widget: "Members with low entries" — anyone with <3 punches left, sorted ascending.
7. **As an owner**, I see "Class utilization" — total attendance per class this month.
8. **As an owner**, I see "Inactive members" — joined-status active but no attendance in 30 days. Churn warning.

---

## API Endpoints

### Classes (`classes`)

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/classes` | Bearer (tenant-scoped) | List classes for current tenant |
| POST | `/api/v1/classes` | owner+ | Create a class |
| PATCH | `/api/v1/classes/{id}` | owner+ | Update name/description/color |
| POST | `/api/v1/classes/{id}/deactivate` | owner+ | Soft-deactivate (no new passes) |
| POST | `/api/v1/classes/{id}/activate` | owner+ | Reactivate |

### Class passes (`class_passes`)

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/passes` | Bearer (tenant-scoped) | List passes (filterable by member, class, status) |
| GET | `/api/v1/members/{id}/passes` | Bearer | All passes for one member |
| POST | `/api/v1/passes` | staff+ | Sell a pass to a member |
| PATCH | `/api/v1/passes/{id}` | staff+ | Update price / expiry / notes |
| POST | `/api/v1/passes/{id}/refund` | owner+ | Refund (sets status=refunded, does not decrement attendance) |

### Attendance (`attendance`)

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/attendance` | staff+ | Record a check-in (member + class) — auto-finds active pass |
| GET | `/api/v1/attendance` | Bearer | List attendance (filterable by member, class, date range) |
| DELETE | `/api/v1/attendance/{id}` | owner+ | Undo a wrong check-in (refunds the entry) |

### Stats (`/api/v1/classes/stats` etc.)

These power the dashboard. Single endpoint per panel, optimized SQL behind it.

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/classes/{id}/utilization?period=month` | owner+ | Total attendance for one class in a period |
| GET | `/api/v1/passes/low-entries?threshold=5` | owner+ | Members with passes about to run out |
| GET | `/api/v1/members/inactive?days=30` | owner+ | Active members with no recent attendance |

---

## Domain (Layer 3)

### Entities

**`domain/entities/gym_class.py`** — named `gym_class` to avoid shadowing Python's `class` keyword.

```python
class GymClass(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str                     # "Spinning"
    description: str | None
    color: str | None             # hex code for dashboard tag color
    is_active: bool               # owner can deactivate without deleting
    created_at: datetime
    updated_at: datetime
```

**`domain/entities/class_pass.py`**

```python
class PassType(StrEnum):
    PUNCH_CARD = "punch_card"   # finite entries
    UNLIMITED = "unlimited"      # date-bounded, no entry count

class PassStatus(StrEnum):
    ACTIVE = "active"
    USED_UP = "used_up"          # punch card hit zero
    EXPIRED = "expired"          # past expires_at
    REFUNDED = "refunded"        # explicit refund

class ClassPass(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    class_id: UUID
    type: PassType
    entries_total: int | None        # NULL for unlimited
    entries_remaining: int | None    # NULL for unlimited
    price_cents: int                 # what the member paid
    purchased_at: date
    expires_at: date | None          # NULL = never expires
    status: PassStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime

    def is_usable(self, today: date) -> bool: ...
    def can_decrement(self) -> bool: ...
```

**`domain/entities/attendance.py`**

```python
class Attendance(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    class_id: UUID
    pass_id: UUID | None             # nullable: lets us record "guest" or "comp" attendance
    attended_at: datetime
    created_at: datetime
```

### Pure logic methods (notable ones)

- `ClassPass.is_usable(today)` — `status == ACTIVE` AND (`expires_at is None` OR `expires_at >= today`) AND (`entries_remaining is None` OR `entries_remaining > 0`)
- `ClassPass.can_decrement()` — only meaningful for punch cards. True if `type == PUNCH_CARD` and `entries_remaining > 0`.

### Exceptions

- `ClassNotFoundError` → 404
- `ClassAlreadyExistsError` → 409 (name collision within tenant)
- `ClassPassNotFoundError` → 404
- `NoUsablePassError` → 409 — member tried to check in but has no active pass for that class
- `PassNotRefundableError` → 409 — already used, refunded, etc.
- `AttendanceNotFoundError` → 404

---

## Service (Layer 2)

### `services/class_service.py`

Standard CRUD with tenant scoping. Owner-only mutations.

### `services/class_pass_service.py`

```python
class ClassPassService:
    async def sell_pass(self, caller, data: ClassPassCreate) -> ClassPass:
        # validates: member belongs to caller's tenant, class belongs to caller's tenant,
        # class is_active, type+entries_total are consistent
        ...

    async def list_for_member(self, caller, member_id) -> list[ClassPass]: ...
    async def list_active_for_member_and_class(self, caller, member_id, class_id) -> list[ClassPass]: ...
    async def refund(self, caller, pass_id) -> ClassPass: ...
```

### `services/attendance_service.py` — the interesting one

```python
class AttendanceService:
    async def record(self, caller, member_id: UUID, class_id: UUID) -> Attendance:
        async with self.uow.begin():  # transaction
            # 1. Validate member + class exist and belong to tenant
            # 2. Find the best active pass for this member+class:
            #    - prefer non-unlimited (use punches first, save unlimited)
            #    - then earliest expires_at (use about-to-expire first)
            pass_ = await self.pass_repo.find_best_active(member_id, class_id)
            if pass_ is None:
                raise NoUsablePassError

            # 3. Insert attendance row, link to pass
            att = await self.attendance_repo.create(
                tenant_id=caller.tenant_id,
                member_id=member_id,
                class_id=class_id,
                pass_id=pass_.id,
                attended_at=now_in_tenant_timezone(caller.tenant),
            )

            # 4. If punch card, decrement
            if pass_.can_decrement():
                new_remaining = pass_.entries_remaining - 1
                new_status = (
                    PassStatus.USED_UP if new_remaining == 0 else PassStatus.ACTIVE
                )
                await self.pass_repo.update(
                    pass_.id, entries_remaining=new_remaining, status=new_status
                )

            return att

    async def undo(self, caller, attendance_id: UUID) -> None:
        # owner+ only. Reverses the decrement if applicable.
        async with self.uow.begin():
            att = await self.attendance_repo.find_by_id(attendance_id)
            # tenant scope check
            await self.attendance_repo.delete(attendance_id)
            if att.pass_id:
                pass_ = await self.pass_repo.find_by_id(att.pass_id)
                if pass_.entries_remaining is not None:
                    # increment back
                    await self.pass_repo.update(
                        pass_.id,
                        entries_remaining=pass_.entries_remaining + 1,
                        status=PassStatus.ACTIVE,  # re-activates if was used_up
                    )
```

**Key business rule:** check-in is one transaction. Either both the attendance row inserts AND the pass decrements, or neither. No half-states.

### `services/dashboard_stats_service.py` (or extend dashboard_service)

Single-purpose query methods that power the owner widgets:

```python
async def members_with_low_entries(tenant_id, threshold=5) -> list[MemberWithPass]: ...
async def class_utilization(tenant_id, class_id, period_start, period_end) -> int: ...
async def inactive_members(tenant_id, since_days=30) -> list[Member]: ...
```

These are aggregation queries — service calls a special `stats` method on the repo that runs optimized SQL.

---

## Adapter (Layer 4)

### Database tables

**`classes`**
```sql
CREATE TABLE classes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  color TEXT,                      -- e.g. "#3B82F6", optional
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX idx_classes_tenant_active ON classes(tenant_id, is_active);
```

**`class_passes`**
```sql
CREATE TABLE class_passes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  class_id UUID NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,
  type TEXT NOT NULL CHECK (type IN ('punch_card','unlimited')),
  entries_total INT,               -- NULL iff type='unlimited'
  entries_remaining INT,           -- NULL iff type='unlimited'
  price_cents INT NOT NULL,
  purchased_at DATE NOT NULL DEFAULT current_date,
  expires_at DATE,                 -- NULL = never expires
  status TEXT NOT NULL CHECK (status IN ('active','used_up','expired','refunded')) DEFAULT 'active',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK (
    (type = 'punch_card' AND entries_total IS NOT NULL AND entries_remaining IS NOT NULL)
    OR (type = 'unlimited' AND entries_total IS NULL AND entries_remaining IS NULL)
  ),
  CHECK (entries_remaining IS NULL OR entries_remaining >= 0),
  CHECK (entries_remaining IS NULL OR entries_remaining <= entries_total)
);

CREATE INDEX idx_passes_member_class ON class_passes(member_id, class_id);
CREATE INDEX idx_passes_tenant_status ON class_passes(tenant_id, status);
-- partial index for the dashboard "low entries" query
CREATE INDEX idx_passes_low_entries
  ON class_passes(class_id, entries_remaining)
  WHERE entries_remaining IS NOT NULL AND status = 'active';
```

**`attendance`**
```sql
CREATE TABLE attendance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  class_id UUID NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,
  pass_id UUID REFERENCES class_passes(id) ON DELETE SET NULL,
  attended_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_attendance_member_time ON attendance(member_id, attended_at DESC);
CREATE INDEX idx_attendance_class_time ON attendance(class_id, attended_at DESC);
CREATE INDEX idx_attendance_tenant_time ON attendance(tenant_id, attended_at DESC);
```

**Why FK choices:**
- `tenant_id ... ON DELETE CASCADE` — deleting a tenant nukes everything (we don't actually hard-delete tenants but it's a safety net)
- `member_id ... ON DELETE CASCADE` — deleting a member (GDPR) wipes their passes + attendance
- `class_id ... ON DELETE RESTRICT` — you can't delete a class that has passes/attendance. Owner must deactivate instead. Preserves history.
- `pass_id ... ON DELETE SET NULL` — if a pass is force-deleted, attendance survives but loses the link. Keeps the historical record of "they did show up".

### Repository methods (notable ones)

`adapters/storage/postgres/class_pass/repositories.py`:

```python
async def find_best_active(member_id, class_id) -> ClassPass | None:
    """
    Returns the pass to use for an attendance record. Picks:
    - status='active' AND (expires_at IS NULL OR expires_at >= today)
    - prefers punch_card over unlimited (use finite first)
    - then orders by expires_at ASC NULLS LAST (use about-to-expire first)
    """

async def find_low_entries(tenant_id, threshold) -> list[tuple[ClassPass, Member]]:
    """
    SELECT cp.*, m.*
    FROM class_passes cp
    JOIN members m ON m.id = cp.member_id
    WHERE cp.tenant_id = $1
      AND cp.status = 'active'
      AND cp.entries_remaining IS NOT NULL
      AND cp.entries_remaining < $2
    ORDER BY cp.entries_remaining ASC
    """

async def expire_old_passes(today) -> int:
    """Background job: flips status='expired' for any active pass past expires_at."""
```

`adapters/storage/postgres/attendance/repositories.py`:

```python
async def class_utilization(tenant_id, class_id, since, until) -> int:
    """COUNT(*) WHERE class_id=X AND tenant_id=Y AND attended_at IN [since,until)"""

async def members_inactive_since(tenant_id, since: datetime) -> list[Member]:
    """
    SELECT m.* FROM members m
    WHERE m.tenant_id = $1 AND m.status = 'active'
    AND NOT EXISTS (
      SELECT 1 FROM attendance a
      WHERE a.member_id = m.id AND a.attended_at >= $2
    )
    """
```

### Migrations

- `0006_create_classes.py` — `classes` table + indexes
- `0007_create_class_passes.py` — `class_passes` table + check constraints + indexes
- `0008_create_attendance.py` — `attendance` table + indexes

### Background job

**`workers/expire_passes.py`** — Celery beat task, runs daily at midnight (tenant-by-tenant timezone-aware later, UTC for v1):

```python
@celery_app.task
def expire_old_passes_task():
    today = date.today()
    n = pass_repo.expire_old_passes(today)
    logger.info("expired_passes_run", count=n)
```

---

## Frontend

### Pages

- **`/settings/classes`** (owner only) — manage class types
  - Table with name, color, is_active, edit/deactivate
  - "Add class" button → small dialog with name + color picker
- **`/passes`** (staff+) — list of all passes, filterable
  - Filter by status, member, class
  - "Sell new pass" button → dialog: pick member, class, type, entries, price, expiry
- **`/members/{id}`** (member detail page — built with Members) gets a passes tab + attendance history
- **`/check-in`** (staff+) — quick-action page for the front desk
  - Search member by name or phone
  - Pick class
  - Click "Check in" → POST /attendance, show confirmation + remaining entries
  - Optimized for one-handed kiosk usage

### Sidebar

Add to `NAV_ITEMS` in `Sidebar.tsx`:
```ts
{ to: "/check-in", label: "צ'ק-אין", icon: "✅", feature: "attendance" },
{ to: "/passes",   label: "כרטיסיות", icon: "🎫", feature: "passes" },
{ to: "/settings/classes", label: "סוגי שיעורים", icon: "🏃", feature: "classes_admin" },
```

### Permissions

Add to the `Feature` union in `permissions.ts`:
- `"attendance"` — staff, sales, owner can check-in members
- `"passes"` — staff (sell + view), owner (refund)
- `"classes_admin"` — owner only (create/edit/deactivate class types)

Note: `"members"` already includes viewing the member detail page; the passes tab shows there even if `"passes"` isn't granted, but the "sell new pass" action is hidden via `canAccess`.

### Dashboard widgets

Replace and add to `GymDashboard.tsx`:

```tsx
<StatCard label="מנויים פעילים"      value={activeCount} />              {/* members feature */}
<StatCard label="צ'ק-אינים החודש"    value={attendanceThisMonth} />      {/* attendance feature */}
<StatCard label="כרטיסיות עומדות לפוג" value={lowEntriesCount} hint="פחות מ-5 כניסות" />
<StatCard label="מנויים לא פעילים"   value={inactiveMembersCount} hint="ללא צ'ק-אין 30 יום" />
```

Each backed by one of the stats endpoints — single tight SQL query each.

---

## Tests

### Backend

| Type | File | What |
|---|---|---|
| Unit | `test_class_pass_entity.py` | `is_usable()`, `can_decrement()`, edge cases (no entries, expired, refunded) |
| Unit | `test_attendance_service.py` | Mocked repos: best-pass selection logic, transaction rollback on error, unlimited vs punch card |
| Integration | `test_class_pass_repo.py` | Real Postgres: check constraints (entries_remaining ≥ 0, ≤ entries_total), find_best_active sort order, find_low_entries query plan |
| Integration | `test_attendance_repo.py` | Aggregations: utilization counts, inactive_since query |
| E2E | `test_check_in_flow.py` | Full HTTP: sell pass → check in → entries decremented → second check in → entries decremented → run out → next check in 409 |
| E2E | `test_attendance_undo.py` | Owner undoes attendance → entries incremented + status=active even if was used_up |
| E2E | `test_dashboard_stats.py` | Stats endpoints return correct counts |

### Frontend

| File | Tests |
|---|---|
| `features/classes/api.test.ts` | All endpoints |
| `features/classes/ClassListPage.test.tsx` | CRUD UI works, only owner sees mutate buttons |
| `features/passes/SellPassDialog.test.tsx` | Validation: punch_card requires entries, unlimited rejects entries |
| `features/checkin/CheckInPage.test.tsx` | Search → pick → check in → success message + remaining entries |
| `features/dashboard/GymDashboard.test.tsx` | New widgets render real data |

---

## Decisions

1. **One feature, three tables.** Classes, passes, and attendance ship together because they don't make sense apart. Splitting would create three half-features that each need the others to be useful.
2. **`type` enum: `punch_card` or `unlimited`.** Captures the two real models gym owners use today. We could add `time_based` (e.g., 1-day pass) later if needed.
3. **`entries_remaining` instead of computing from attendance.** Trade-off: denormalized for speed and simplicity. Reading "how many left" is one column lookup, not an aggregation. Background job re-syncs nightly as a safety net (optional, can defer).
4. **Service runs check-in as a transaction.** Either attendance row inserts AND pass decrements, or neither. No half-states, ever.
5. **`find_best_active` picks the pass automatically.** Staff doesn't pick which pass to use — backend prefers punch cards over unlimited (use the finite ones first), then earliest-expiring. Reduces front-desk cognitive load.
6. **`pass_id` on attendance is nullable.** Lets us record "guest" / "comp" / "trial" attendance with no pass. Real-world gyms do this.
7. **Class deletion is RESTRICTed.** Owner must deactivate instead. Preserves historical attendance reports — "Spinning had 200 attendees last year" still works even if they stopped offering it.
8. **Refund is a status, not a delete.** `status='refunded'` preserves the record + price for accounting. Refund doesn't undo past attendance.
9. **Attendance time = `attended_at`.** Recorded server-side at request time, in tenant timezone. Front desk doesn't pick a date — they record "now". Backdated entries possible via PATCH for owners (future).
10. **Stats endpoints are read-only and dashboard-specific.** Don't try to make `GET /attendance?aggregate=count_by_class` clever. Build named endpoints (`/classes/{id}/utilization`) — simpler API, optimized SQL behind each.
11. **Daily expire job is Celery beat.** Not strictly required (queries can filter `expires_at < today`), but materializing the status as `expired` makes dashboards faster and queries simpler.
12. **`color` is free text.** Hex code suggested in UI, no validation. Owner picks. Doesn't matter if it's invalid CSS — frontend has a fallback.
13. **No class scheduling in this feature.** "Spinning Mondays at 7am" is a calendar problem and a much bigger UX. Defer to a future `class_sessions` feature.

---

## Open questions

1. **Should we add `daily_limit` to passes?** Some gyms cap "1 entry per day even if you have a punch card". Easy column. Defer until a real customer asks.
2. **Should attendance support `walk_in` (no member)?** Drop-in customers without a member record. Probably YES — captures revenue, but then needs `walk_in_payment_cents`. Decide before building.
3. **Should the check-in page work offline?** Front-desk WiFi flakes happen. Hard problem (sync, conflict resolution). Defer until somebody complains.
4. **Should passes expire automatically on member cancel?** When a member is cancelled, do their active passes flip to `refunded` or stay `active` for record-keeping? Vote: stay `active` but member can't use them (no member = no check-in). Simpler.
5. **Multi-class passes?** "Anything pass — works for any class." Could be modeled as `class_id IS NULL`. Simple variant. Defer until requested.
6. **Family / shared passes?** "Mother + daughter share a 10-pack." Defer indefinitely, complex.

---

## Migration plan

Three PRs, each independently shippable:

1. **Backend PR 1: classes** — `classes` table + entity + service + routes + tests. Frontend page is owner-only settings, low risk.
2. **Backend PR 2: passes** — `class_passes` table + entity + service + routes + tests. Depends on classes existing.
3. **Backend PR 3: attendance + stats** — `attendance` table + service (transactional check-in) + dashboard stats endpoints + Celery beat job. Depends on passes existing.

Each backend PR followed by its frontend PR. Roughly 1-2 days each.

---

## Related docs

- [`spec.md`](../spec.md) — product spec
- [`members.md`](./members.md) — parent feature, class passes FK to members
- [`tenants.md`](./tenants.md) — every table tenant-scoped
- [`../skills/build-backend-feature.md`](../skills/build-backend-feature.md)
- [`../skills/build-frontend-feature.md`](../skills/build-frontend-feature.md)
