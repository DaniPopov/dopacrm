# DopaCRM — Business Logic

> Cross-feature rules that span entities. Per-feature docs under
> `docs/features/` describe the shape of each module; this doc owns
> the **connective tissue** between them — the rules that don't fit in
> any single module because they reach across several.
>
> **Living document.** When a new rule starts to span two features,
> it lands here with a short rationale. When a rule is contained to one
> feature, it stays in that feature's doc.
>
> Last updated: 2026-04-24.

---

## Why this doc exists

Before this doc, cross-feature rules (how attendance attributes to a
coach, how an entitlement window resets, when a subscription is "live"
for the purpose of check-ins) had to be inferred by reading three
feature specs side-by-side. Doing that once = fine; doing it for every
new feature = bugs.

This is the single place a reader answers:

- *"What actually counts as an entry, and when is it 'effective'?"*
- *"What subscription states allow a check-in?"*
- *"When an owner edits a pay rule, what happens to past payroll?"*
- *"When an entity becomes inactive (frozen / cancelled), what still
  happens vs. what stops?"*

Rules here are **authoritative**. If a feature doc contradicts this
file, this file wins; patch the feature doc.

---

## 1. The "live" subscription — the gate for everything

Many features gate on "is this member currently paying?" — check-in,
attendance summary, leads-to-members conversion, even some reporting.
One definition serves them all.

**A subscription is LIVE iff:**

```
status IN ('active', 'frozen')
AND NOT (status = 'active' AND expires_at < today)
```

Postgres constraint already expresses half of this via the partial
UNIQUE index (`one live sub per member`). The rest is enforced in
`SubscriptionRepository.find_live_for_member`.

**Implications for every downstream feature:**

- Attendance refuses a check-in if no live sub exists → 409
  `MemberHasNoActiveSubscriptionError`. Drop-ins must be modeled as a
  one-time plan with its own sub.
- Coach earnings use `class_entries` only, not subscriptions — but
  every entry has a non-null `subscription_id` because of the rule
  above. Indirect dependency; reliable.
- Payments records a payment even if no sub exists (ad-hoc cash). The
  payment may have `subscription_id = NULL`. That's fine — the
  "live" rule only gates ATTENDANCE, not revenue.
- `status='replaced'` is NOT live. Plan-change mid-cycle spawns a new
  active sub; the old one holds the event history.

**Why `frozen` counts as live:** the gym froze billing, but the member
still pays on unfreeze + may walk in for pre-paid sessions. Check-in
stays open; quota math uses the same entitlements.

---

## 2. Entitlement attribution — exact class beats wildcard

When a member has a sub and walks into a class, pick ONE entitlement
row to count against.

**Precedence:**

1. **Exact class match** — `entitlement.class_id == entry.class_id`.
2. **Wildcard entitlement** — `entitlement.class_id IS NULL`
   (covers any class).

If no row matches either, the entry is **not covered** → override
required.

**Concrete example:**

Plan has:
- Entitlement A: `class_id=yoga`, `quantity=3`, `reset_period=weekly`
- Entitlement B: `class_id=NULL`, `quantity=unlimited`

Member attends yoga → decrements A (exact match wins, even though B
would also allow it). Member attends boxing → counts against B. This
matters for reporting — A's "3/week" cap stays accurate.

**When there are multiple wildcards** (weird but legal): return the
first one; backend has a deterministic `ORDER BY entitlement.id`. Not
owner-facing — the UI doesn't let you create two wildcards.

---

## 3. Reset-window math — one function, five shapes

Every quota counting query needs "how much has been used since the
window start?". Five reset periods, one helper:

| reset_period | window start |
|---|---|
| `weekly` | Sunday 00:00 Asia/Jerusalem of the current week |
| `monthly` | 1st of month 00:00 Asia/Jerusalem |
| `billing_period` | `subscription.started_at + N × billing_days` for the current N |
| `never` | `subscription.started_at` — total across sub lifetime |
| `unlimited` | short-circuits — no window, always allowed |

**Implementation**: `attendance_service._compute_window_start`.

**Day-0 constants:**

- `billing_days` per `BillingPeriod`: monthly=30, quarterly=90,
  yearly=365. (Simple approximation — revisit if a real gym complains
  about Feb-29 edge cases.)
- Weekly resets on **Sunday** because Israel's work week starts
  Sunday. Tenant timezone hard-coded to Asia/Jerusalem in v1; add a
  `tenants.timezone` column when we onboard non-IL gyms.
- All boundaries computed in the tenant's timezone, not UTC. The DB
  column is TIMESTAMPTZ; we convert at query time, not storage.

---

## 4. "Effective" entries — the undone_at shadow

Any query that counts / reports on entries MUST filter out undone:

```sql
WHERE undone_at IS NULL
```

The partial index `idx_entries_effective` is exactly this filter,
pre-applied. A forgotten filter means a dashboard overcounts, payroll
overpays, quota math lets too many in.

**Rule:** no query in the code that touches `class_entries` should
omit `undone_at IS NULL` unless it's a raw audit endpoint whose
purpose is to show undone rows.

**When undo happens:**
1. Row gets `undone_at=now`, `undone_by=user`, `undone_reason=?`.
2. Quota refunds — next check-in sees one more slot available.
3. Payroll reverses — the entry no longer counts toward the coach's
   per-attendance total. Running the earnings report for the period
   now gives a lower number. **This is correct** — the earnings
   endpoint reflects the current truth. If the period has already
   been paid out, payroll is overpaid and the gym needs to reconcile;
   that's a Payments concern, not a Coaches one.

---

## 5. Coach attribution — session first, weekday fallback

Every `class_entries` row gets a `coach_id` (and optionally a
`session_id`) set server-side at insert. The order of precedence:

```
# 1. SCHEDULE BRANCH — only if tenant has Schedule feature enabled.
if is_feature_enabled(tenant, "schedule"):
    session := class_sessions WHERE class_id = entry.class_id
                            AND status = 'scheduled'
                            AND starts_at - 30min <= entry.entered_at <= ends_at + 30min
                            ORDER BY ABS(starts_at - entry.entered_at) LIMIT 1
    if session is not None:
        entry.session_id := session.id
        entry.coach_id   := session.head_coach_id
        method           := "session"
        return

# 2. WEEKDAY BRANCH — fallback when Schedule is off OR no matching session.
weekday     := entry.entered_at.astimezone(tenant_tz).weekday()
candidates  := class_coaches WHERE class_id = entry.class_id
                         AND (weekdays IS EMPTY OR weekday IN weekdays)
                         AND starts_on <= entry.entered_at::date
                         AND (ends_on IS NULL OR ends_on >= entry.entered_at::date)
                         AND coach.status = 'active'

if len(candidates) == 1:     entry.coach_id := candidates[0].coach_id
elif any is_primary:         entry.coach_id := first is_primary row
else:                        entry.coach_id := ORDER BY coach_id ASC LIMIT 1
                                              (deterministic, corrigible)

if no candidate at all:      entry.coach_id := NULL + WARN log event
method := "weekday" | "null"
```

The 30-minute tolerance on the session lookup lets members arrive
early or leave late without breaking attribution. If multiple
sessions overlap (unusual — same class scheduled twice at once),
the closest `starts_at` wins.

**Invariants:**

- `session_id` and `coach_id` are written **once** at insert. Changing
  `class_sessions` or `class_coaches` later does NOT update history.
  Payroll for past periods is locked.
- Owner can correct `coach_id` via
  `POST /attendance/{id}/reassign-coach` — logs
  `attendance.coach_reassigned`. `session_id` is not user-editable
  post-insert (cancel the session instead).
- The `attendance.coach_attributed` event's `method` field records
  which branch fired (`session` / `weekday` / `null`) — owner audit
  surface for "how many drop-ins did I have last month?" (entries
  with `method='null'` or `session_id IS NULL` answer that).
- If the tenant toggles Schedule OFF after entries have been recorded
  with `session_id`, those entries keep their `session_id` — history
  is immutable. New entries fall through to weekday.

---

## 6. Pay-model semantics

Three models, one service, three different math paths.

### `fixed`

Monthly salary. Pro-rated by day when the earnings query spans a
partial month.

```
for each calendar month touched by [from, to]:
    overlap_days := days in (month ∩ [from, to])
    cents += monthly_cents × overlap_days / days_in_that_month
round once at the end
```

Leap years use Python `calendar.monthrange`. Do NOT use a 30-day
constant.

### `per_session`

Branches on whether the tenant has Schedule enabled:

- **Schedule ON (post-Schedule-PR):**
  ```
  count(class_sessions WHERE
      head_coach_id = coach
      AND class_id  = link.class_id
      AND status    = 'scheduled'
      AND starts_at ∈ [from, to])
  ```
  Deterministic. A coach who shows up for a session that no one
  attends still gets paid. A cancelled session contributes 0
  (intentional — see `schedule.md` §5 "Cancellation pay = no pay").

- **Schedule OFF (original v1):** count distinct days the coach had
  ≥1 attributed entry for this class. Approximation — surfaces in
  the earnings response note as "v1 per-session approximation" so
  the owner knows why the number may differ from their expectation.

Which branch runs depends on `tenant.features_enabled.schedule`. The
earnings endpoint's response includes a `per_session_source` field
(`'scheduled_sessions'` or `'distinct_entry_days'`) so the UI can
show the right copy.

**Why the branch instead of migrating all tenants to the Schedule
math?** Tenants that never enable Schedule still need `per_session`
pay to work. Forcing Schedule + templates on them would violate the
Feature Flags contract (§12 below).

### `per_attendance`

`pay_amount_cents × count(effective entries attributed to this coach
for this class in [from, to])`. Override entries count by default;
the response breakdown shows `overrides_counted` so the owner can
sanity-check.

### Multiple rate rows per link

Rate changes = end the current `class_coaches` row
(`ends_on = yesterday`), insert a new one (`starts_on = today`).
Each is clipped to the earnings window independently and summed.
Do NOT mutate `pay_amount_cents` in place — you'd silently rewrite
history.

---

## 7. State machines — the one-frame reference

Every entity with a "can I act on this now?" question follows the
same pattern: terminal states go red, reversible ones go amber.

| Entity | States (terminal in CAPS) | Key transitions |
|---|---|---|
| Tenant | trial, active, suspended, CANCELLED | suspend ↔ activate; cancel is terminal |
| Member | active, frozen, CANCELLED | freeze ↔ unfreeze; cancel terminal |
| Subscription | active, frozen, expired, CANCELLED, REPLACED | freeze ↔ unfreeze; renew from active|expired; change_plan → spawns new active, old → REPLACED; cancel terminal |
| ClassEntry | recorded, UNDONE (via `undone_at`) | undo only within 24h; no re-enable |
| Coach | active, frozen, CANCELLED | freeze ↔ unfreeze; cancel terminal |
| Lead | new, contacted, trial, CONVERTED, lost | new→contacted→trial→converted (or any direct skip forward); lost reachable from any open state and reopens to contacted; converted is terminal and only reachable through the convert endpoint (which atomically writes Member + Subscription + status_change) |

**Rule of thumb applied everywhere:**

- Transitions that mutate business state **MUST** emit a structlog
  event carrying `tenant_id`, `entity_id`, `from`, `to`, `by_user`,
  and any relevant payload.
- Terminal states are expressed as `status = 'cancelled'` /
  `status = 'replaced'` + a corresponding timestamp column, not a
  row deletion. Hard deletes only happen for truly ephemeral data
  (session tokens, cache rows).

---

## 8. Tenant scoping — non-negotiable

Every table that has a `tenant_id` column enforces:

1. **Repository method signatures** take `tenant_id` explicitly.
   Never derive it from the object under mutation — derive it from
   the caller (JWT's `tenant_id`).
2. **Service methods** take `caller: TokenPayload`. They extract
   `tenant_id` from the caller, verify it against the row's
   `tenant_id`, and 404 on mismatch. `403` is NOT used for
   cross-tenant access — 403 leaks existence.
3. **`test_cross_tenant_isolation.py`** has one probe per gym-scoped
   endpoint. A new endpoint without a probe = review-block.
4. **`super_admin` bypasses** the tenant check — platform support.

Details in [`security/cross-tenant-isolation.md`](./security/cross-tenant-isolation.md).

---

## 9. Money — integer cents, one currency per tenant

- Every monetary column is `_cents INTEGER`. Never `NUMERIC`, never
  `FLOAT`.
- Arithmetic (pro-rating, totals, discounts) is done on cents, rounded
  at the LAST step with banker's rounding (`round(x, 0, HALF_EVEN)`).
- `tenants.currency` (ILS default) is THE currency for every money
  column under that tenant. Payments, subscription prices, pay amounts,
  dashboard totals — all share it.
- Multi-currency is explicitly out of scope until we onboard a
  non-IL gym. When that lands, it's a migration (add `currency` column
  per-row on money-bearing tables) + an audit + FX hooks. Flagged
  here so nobody sneaks it in piecemeal.

---

## 10. Immutability rules (what CANNOT be rewritten)

These columns/tables are append-only or write-once. Touching them
breaks audit; the code-review bar is high.

| Table | Write-once field(s) | Why |
|---|---|---|
| `payments` | whole row | Legal/accounting. Corrections = new row with negative amount. |
| `class_entries` | whole row (soft-delete via `undone_at` only) | Audit of who came when. Undo is a shadow, not an erase. |
| `class_entries.coach_id` | set at INSERT, never UPDATED by service | Locked payroll history. Admin `reassign-coach` is the only legitimate override. |
| `subscription_events` | whole row | The audit log IS the state machine's memory. |
| `subscriptions.price_cents` | set at INSERT | Shields the member from retroactive plan price changes. |
| `subscriptions.started_at` / `expires_at` | mutated ONLY by freeze/unfreeze/renew/replace | Anywhere else = bug. |
| `class_coaches.pay_amount_cents` | mutation discouraged; prefer end-row + insert-row | Protects past earnings from silent rewrites. Enforced in UI, not DB. |

**Corollary — what IS mutable:** `status` transitions, JSONB
`custom_fields` / `custom_attrs`, and anything whose audit history
lives in a separate `_events` table.

---

## 11. Timezone — one today, one tomorrow

Rule: **all date math uses `Asia/Jerusalem` today, always**.

- Weekly reset boundaries, reset windows, pay pro-ration month slices,
  "today's check-ins", all work off the tenant's local midnight.
- Storage is TIMESTAMPTZ (UTC). Conversion happens at query time in
  the service, never stored denormalized.
- `utcnow()` stays in the code for naming consistency, but "today"
  inside business rules means tenant-local today. A check-in at 01:30
  UTC on Monday is still "Sunday" for a gym in Israel (UTC+3) — quota
  counts against Sunday's window.
- When `tenants.timezone` ships (multi-region), the constant
  `"Asia/Jerusalem"` becomes `tenant.timezone`. All call sites already
  go through one helper, so the migration is two lines.

---

## 12. Permission layering — four checks, always

Every mutation endpoint in a gated feature is checked four times:

1. **JWT validity** (middleware) — forged / expired tokens → 401.
2. **Role gate** (service) — e.g. "owner or above". `InsufficientPermissionsError` → 403.
3. **Tenant feature gate** (service) — for gated features only:
   `is_feature_enabled(tenant, feature)` must be True.
   `FeatureDisabledError` → 403. Ungated features skip this step.
4. **Tenant scope** (service) — resource's `tenant_id` must match
   caller's. Mismatch → 404 (not 403).

A single missed layer = a security bug. All four must be present for
gated features; ungated features skip #3.

**Why feature gate goes between role gate and tenant scope:**

- After role gate: no point checking the feature is enabled if the
  user doesn't have the role to use it anyway. Role gate gives 403
  first.
- Before tenant scope: if the feature is disabled, we want 403
  "feature not enabled" — NOT 404 "resource not found," which would
  leak that the resource exists.

**403 vs 404 distinction:**

- 403 = "we know you, we know the resource exists, we refuse." Used
  for role + feature checks.
- 404 = "this resource doesn't exist for you." Used for tenant
  scope to avoid existence leaks.

Reads follow the same pattern except the role gate is usually weaker
(any tenant user). Feature gate + tenant scope are **identical** for
reads and writes.

**Gated features today:** `coaches`, `schedule`, `leads`.
**Ungated features today:** `members`, `classes`, `plans`,
`subscriptions`, `attendance`, `users`, `tenants`.

---

## Related

- `spec.md` — product overview, target users, roadmap.
- `backend.md` — how the 4 layers (api → service → domain ← adapter) fit.
- `security/cross-tenant-isolation.md` — §8 enforced in detail.
- `standards/architecture.md` — project structure + layer rules.
- `features/feature-flags.md` — the mechanism §12 step 3 checks.
- `features/schedule.md` — session-based attribution (§5) + updated
  `per_session` pay (§6).
- `features/leads.md` — pipeline state machine (§7 row) + the
  cross-feature convert transaction that writes Lead + Member +
  Subscription + activity in one Postgres txn.
- `features/*.md` — per-feature specs that lean on this doc.
