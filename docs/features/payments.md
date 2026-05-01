# Feature: Payments

> **Status:** Planned. Spec for review — not yet implemented.
>
> **Order:** Build AFTER Leads (shipped). Ships as a **basic feature** —
> always on for every tenant, no flag. Revenue tracking is the CRM, not
> a value-add.
>
> **What this is:** an append-only ledger of money members actually paid
> the gym. v1 is **manual entry** (staff types in cash collected, card
> charges, bank transfers); processor integration (Stripe / GoCardless /
> Israeli credit clearing) is Phase 5.

---

## Summary

Until now, every "revenue" widget on the dashboard says **בקרוב**
(coming soon) because we have plans + subscriptions but no record of
money actually changing hands. Payments closes that gap: every
collected ₪ becomes a row in the `payments` table, owners see real
revenue numbers, and the gym's accountant can reconcile.

Concretely, this feature builds:

- **A `payments` table** — one row per collected payment. Tied to a
  member (always) and a subscription (optional — drop-in / one-off
  payments don't need a sub). Carries amount, currency, payment
  method, and the date the money was actually received (which can
  differ from when the row was entered).
- **Append-only ledger semantics** — no UPDATE, no DELETE through the
  API. Mistakes are corrected by recording a **negative-amount
  refund row** that points back at the original. The original stays.
  Auditor-friendly: every entry that ever existed is still there.
- **A `/payments` page** — list view, filterable by member /
  subscription / paid_at range / method. The accountant's view.
- **Member detail page section** — "Payments" tab on each member
  showing their pay history + a prominent **"+ Record Payment"**
  button next to their active subscription.
- **`POST /payments`** + **`GET /payments`** + **`GET /payments/{id}`**
  + **`POST /payments/{id}/refund`** — the v1 endpoint surface.
- **Dashboard wire-up** — the "Revenue this month" / "Revenue last
  month" / "MoM change" / "Revenue per plan" / "Average revenue per
  member" widgets all flip from `בקרוב` placeholders to real numbers.
- **Permission gates** — staff+ writes (gym ops job); owner+ refunds
  (destructive-ish, owner-gated to prevent honest staff mistakes
  from corrupting the books); read for any tenant role except coach.

---

## Why it's a separate feature (not folded into Subscriptions)

- **Different lifecycle.** A subscription lives for months; a payment
  is a single moment. Mixing them muddles "active subs" with "money
  in the till."
- **Different write pattern.** Subs change rarely (create, freeze,
  renew, cancel — a handful per member per year). Payments accrete
  monthly (recurring) or daily (drop-ins). Separate tables = separate
  indexes = cheap range queries for the dashboard.
- **Different audit posture.** Subs have a state machine; payments
  are append-only with a refund convention. The "no edit, no delete"
  rule wouldn't fit subscriptions (they freeze, renew, change-plan).
- **Different consumer.** The accountant cares about payments. The
  gym owner cares about subs *for billing decisions* and payments
  *for the bottom line*. Two consumers, two tables.

---

## Where this sits in Phase 3

```
  Phase 2 (Core CRM) — shipped:
    Members / Classes / Plans / Subscriptions / Attendance

  Phase 3 (Operations):
    Coaches                  ✓ shipped
    Schedule + Feature Flags ✓ shipped
    Leads                    ✓ shipped
    Payments                 ← THIS DOC
    Dashboard metrics wiring (last — Payments is the biggest unblocker)

  Phase 5 (Integrations):
    Stripe / GoCardless / Israeli credit clearing
    CSV import of historical payments
```

Payments is the second-to-last Phase 3 feature because it depends on
nothing else (members + subs already exist) but the dashboard depends
on it. Shipping Payments → Dashboard becomes possible.

---

## User stories

1. **As a gym owner**, walk-in member Yael signs up for the 250₪
   monthly plan and hands me 250₪ cash. I enroll her (existing
   Subscriptions flow), then click the prominent **"+ Record
   Payment"** button next to her new subscription on her detail page.
   Dialog auto-fills 250₪ + cash + today; I click save. Two clicks,
   ~30 seconds.
2. **As an owner**, Yael did a free trial last week. Today she
   converts (Leads → Convert) but says "I'll bring the cash on
   Sunday." Sunday I click **"+ Record Payment"** on her profile,
   pick "cash", enter 250₪, set `paid_at = today`. Sub was active
   since the convert; payment is logged Sunday. Independent flows.
3. **As a sales rep**, Maya pays 100₪ now and 150₪ next week (she
   forgot her wallet). I record two separate payment rows over the
   two weeks; total = 250₪. The dashboard shows 100₪ in week 1 and
   150₪ in week 2.
4. **As an owner**, I made a mistake — typed 25₪ instead of 250₪
   yesterday. I click the row → **"החזר תיקון"** (correction refund) →
   confirm. A new row with `amount_cents = -2500` and a note "תיקון
   טעות" is created. The original row stays. I record a fresh 250₪
   row to make the dashboard correct.
5. **As an owner**, on the dashboard I see "הכנסות החודש: 18,400 ₪
   (+12% מחודש קודם)". Real numbers, finally. Below it, a small
   pie chart shows the split: Monthly = 14,200 ₪, Quarterly =
   3,000 ₪, Drop-in = 1,200 ₪.
6. **As an accountant** working from the gym owner's data export
   later, I open `/payments` and filter by `paid_at` between Jan 1
   and Mar 31. I see every payment with member name, amount, method,
   notes. I export to CSV (future enhancement) or copy-paste into
   the gym's bookkeeping software.
7. **As staff**, I'm at check-in and a member tries to pay me 50₪
   for a drop-in class (no subscription). I record a payment with
   `subscription_id = NULL`, member set to her, amount 50₪, method
   cash, notes "drop-in yoga". The flow doesn't require a sub.
8. **As an owner**, super_admin's "Total platform revenue" widget
   on the platform dashboard sums revenue across all my tenants.
   Before Payments, it was a placeholder. After: real platform-wide
   numbers.

---

## Decisions (baked in from the back-and-forth)

### 1. Basic feature — always on, no flag

Unlike Coaches / Schedule / Leads, Payments is not gated. Every gym
has revenue; tracking it is the **definition** of a CRM, not an
optional add-on. No `tenants.features_enabled.payments` key.

### 2. Manual entry only in v1

Staff types in payments after collecting them. No card processing,
no API integrations, no bank-statement matching. Two reasons:

- Israeli credit clearing (Tranzila, IsraCard, Pelecard, etc.) is a
  per-merchant integration nightmare; doing it well is its own Phase 5
  feature.
- Even when processor integration ships, the *manual entry* path
  stays — gyms still take cash for drop-ins, transfers via Bit, etc.

The data model reserves an `external_ref TEXT` column from day 1 so a
future Stripe webhook can stamp `external_ref = "ch_3OqA..."` without
a migration.

### 3. Subscription create does NOT auto-record a payment

Two flows, two clicks. The owner explicitly records each payment
after they collect the money. Rationale + worked examples in the
"Where this sits with Subscriptions" section below — the short
version is: trial-converts, partial payments, advance payments, and
backdated payments all become awkward special cases if the dialogs
are bundled. Keeping them separate makes every flow trivial; the
common "walk-in pays in full immediately" case costs one extra click
that we counter with a prominent button placement.

The frontend mitigates the extra click by surfacing **"+ Record
Payment"** prominently on the member detail page right next to the
subscription, so the walk-in flow is two clicks total: enroll, then
record. The dialog auto-fills the plan price + the active sub's
currency + today's date so the user just hits save.

### 4. Refunds via negative-amount rows (append-only)

A refund is a new row with `amount_cents < 0` referencing the
original payment via `refund_of_payment_id`. The original row is
untouched. Three reasons:

- **Auditable.** Every entry that ever existed still exists. No
  mutation, no soft-delete, no hidden state.
- **Sums work.** "Net revenue" = `SUM(amount_cents)`. Refunds
  subtract automatically. No special-case query.
- **Matches accounting.** Real-world bookkeeping records refunds as
  separate entries with negative or credit-side amounts. Gym
  accountants will find this familiar.

The dedicated **`POST /payments/{id}/refund`** endpoint takes an
optional reason + optional partial amount (default = full refund).
Owner+ only — staff can record payments, only the owner can refund.

A refund row's `subscription_id` is copied from the original so
revenue-per-plan reports still group correctly.

### 5. No `status` field — every row is real money

We do NOT model "pending" or "failed" payments in v1. Reasons:

- "Pending" = money owed but not yet received = the *absence* of a
  payment row for that period. Don't model absence as a status; just
  query for missing rows.
- "Failed" = a Stripe charge that didn't go through = a Phase 5
  concern. v1 is manual entry, so failures don't enter the system.

Every row is **collected money**. If something is uncertain, it's
not a payment yet.

### 6. Currency snapshot from `tenants.currency`

One currency per tenant (per `crm_logic.md` §9). The payment row
copies `tenants.currency` at insert time. We store the snapshot so a
future "tenant changes currency" (rare) doesn't retroactively
recompute history. Matches the price-snapshot pattern on
Subscriptions.

### 7. `paid_at` separate from `created_at`

`paid_at` = when the money actually changed hands (member's
perspective). `created_at` = when the row was entered into DopaCRM.

These differ when:
- Owner enters yesterday's cash on the next morning (`paid_at` = yesterday)
- Bookkeeper batches a week of bank-transfer entries on Friday
- Historical migration from the old system

Dashboard reports use **`paid_at`** for "revenue this month" — the
business-level question. `created_at` is just an audit timestamp.

---

## State machine

Payments don't have one. They're append-only data rows. The closest
thing to a "transition" is: **payment → refund** = a fresh row, not a
status change.

```
  ┌──────────┐   POST /payments/{id}/refund
  │ payment  │──────────────────────────────► ┌──────────────┐
  │ (1000₪)  │                                 │ refund row   │
  └──────────┘                                 │ (-1000₪)     │
                                                │ refund_of_…  │
                                                └──────────────┘
```

Both rows live forever. `SUM(amount_cents)` for the member = 0,
which is the correct answer.

---

## Data model

### Migration `0014_create_payments`

A single new table. No backfill (existing tenants just have zero
payments until they start recording).

### `payments` table

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` |
| tenant_id | uuid | NOT NULL, FK → `tenants.id` ON DELETE CASCADE |
| member_id | uuid | NOT NULL, FK → `members.id` ON DELETE RESTRICT — preserve payment history when a member is hard-deleted (which we don't do today, but the constraint encodes the intent) |
| subscription_id | uuid | nullable, FK → `subscriptions.id` ON DELETE SET NULL — drop-ins / one-off payments don't have a sub; subs can be cancelled but the payment history stays |
| amount_cents | bigint | NOT NULL — signed; negative for refund rows. `bigint` so a single tenant's lifetime sum never overflows |
| currency | text | NOT NULL — snapshot from `tenants.currency` at insert time |
| payment_method | text | NOT NULL, CHECK in (`cash`, `credit_card`, `standing_order`, `other`) — same enum as `subscriptions.payment_method` |
| paid_at | date | NOT NULL — when the money actually moved. Backdate-able. |
| notes | text | nullable — free text (receipt #, "drop-in yoga", "credit for friend referral") |
| refund_of_payment_id | uuid | nullable, FK → `payments.id` ON DELETE RESTRICT — set on refund rows pointing at the original |
| external_ref | text | nullable — reserved for Phase 5 (Stripe charge id, bank transfer ref) |
| recorded_by | uuid | nullable, FK → `users.id` ON DELETE SET NULL — who entered the row |
| created_at | timestamptz | NOT NULL, default `now()` |

**Indexes:**
- `idx_payments_tenant_paid` on `(tenant_id, paid_at DESC)` — the
  dashboard's primary query ("revenue this month")
- `idx_payments_member_paid` on `(member_id, paid_at DESC)` — member
  detail page
- `idx_payments_subscription` on `(subscription_id, paid_at DESC)` —
  per-sub revenue rollups (partial: `WHERE subscription_id IS NOT NULL`)
- `idx_payments_refund_of` on `(refund_of_payment_id)` — list refunds
  on a payment (partial: `WHERE refund_of_payment_id IS NOT NULL`)

**CHECK constraints:**
- `ck_payments_amount_nonzero` — `amount_cents <> 0`. Zero-amount
  rows mean nothing.
- `ck_payments_refund_negative` — when `refund_of_payment_id IS NOT
  NULL`, `amount_cents < 0`. Refunds are always negative.

**No UNIQUE on `external_ref`** — gateways occasionally retry with
the same id; service layer dedupes when Phase 5 lands.

---

## Domain (Layer 3)

### `domain/entities/payment.py`

```python
class Payment(BaseModel):
    id: UUID
    tenant_id: UUID
    member_id: UUID
    subscription_id: UUID | None
    amount_cents: int  # signed
    currency: str
    payment_method: PaymentMethod  # reused from subscription.py
    paid_at: date
    notes: str | None
    refund_of_payment_id: UUID | None
    external_ref: str | None
    recorded_by: UUID | None
    created_at: datetime

    def is_refund(self) -> bool:
        return self.refund_of_payment_id is not None

    @property
    def signed_amount(self) -> int:
        """Convenience — already signed; refunds are negative."""
        return self.amount_cents
```

No state machine, no transition methods. Pure data row.

### Exceptions (added to `domain/exceptions.py`)

- `PaymentNotFoundError` → 404
- `PaymentAmountInvalidError` → 422 (zero amount, or refund with
  positive amount)
- `PaymentRefundExceedsOriginalError` → 409 (partial refund > original
  amount)
- `PaymentAlreadyFullyRefundedError` → 409 (cumulative refunds = the
  original; further refund attempts blocked)

---

## Service (Layer 2)

### `services/payment_service.py`

```python
class PaymentService:
    async def create(
        self, *, caller, member_id, amount_cents, payment_method,
        paid_at=None, subscription_id=None, notes=None, external_ref=None,
    ) -> Payment: ...

    async def get(self, *, caller, payment_id) -> Payment: ...

    async def list_for_tenant(
        self, *, caller,
        member_id=None, subscription_id=None,
        paid_from=None, paid_to=None,
        method=None, include_refunds=True,
        limit=50, offset=0,
    ) -> list[Payment]: ...

    async def list_for_member(self, *, caller, member_id) -> list[Payment]: ...

    async def refund(
        self, *, caller, payment_id, amount_cents=None, reason=None,
    ) -> Payment: ...
        # amount_cents=None → full refund
        # amount_cents=N    → partial refund (must be ≤ remaining)

    async def revenue_summary(
        self, *, caller, paid_from, paid_to,
    ) -> RevenueSummary: ...
        # Backs the dashboard widgets.
```

### Business rules

- **Tenant scoping** — every read/write asserts `tenant_id ==
  caller.tenant_id`. Cross-tenant returns 404.
- **Permission baseline** — owner / sales / staff / super_admin can
  read + record payments; coach is blocked. **Refund is owner +
  super_admin only.**
- **Cross-resource validation** — `member_id` must be in the same
  tenant. If `subscription_id` is provided it must (a) be in the same
  tenant AND (b) belong to the same `member_id`.
- **Currency snapshot** — service reads `tenants.currency` and stamps
  it on the row. Caller cannot override.
- **Refund math** — service computes `cumulative_refunded` = sum of
  refund rows pointing at the original, asserts
  `cumulative_refunded + new_refund ≤ original_amount`, raises
  `PaymentRefundExceedsOriginalError` otherwise.
- **Append-only** — no `update` method on the service. There's no API
  to modify an existing payment row.
- **`paid_at` backdate window** — defaults to today if omitted.
  Future-dated entries (`paid_at > today`) are rejected (probably a
  typo). Backdating allowed up to 365 days; further back is allowed
  via a separate `backdate=true` flag (audit-logged).

---

## Adapter (Layer 4)

### Repository

`adapters/storage/postgres/payment/repositories.py`:

- `create(tenant_id, ...) -> Payment`
- `find_by_id(payment_id) -> Payment | None`
- `list_for_tenant(...) -> list[Payment]` (filters as listed in
  service; ordered by `paid_at DESC`)
- `list_for_member(tenant_id, member_id) -> list[Payment]`
- `list_refunds_for(payment_id) -> list[Payment]` — refund chain
- `sum_for_range(tenant_id, paid_from, paid_to) -> int` — net revenue
  including refunds
- `sum_by_plan_for_range(tenant_id, paid_from, paid_to) -> dict[UUID, int]`
  — JOIN against subscriptions for the per-plan widget
- `count_active_paying_members(tenant_id, since: date) -> int` — for
  ARPM (avg revenue per paying member)

---

## API (Layer 1)

### Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/payments` | staff+ | Record a payment. Body: `{member_id, amount_cents, payment_method, paid_at?, subscription_id?, notes?, external_ref?}`. Currency is auto-snapshotted from tenant. |
| GET | `/api/v1/payments` | Bearer (tenant-scoped) | List with filters: `member_id`, `subscription_id`, `paid_from`, `paid_to`, `method`, `include_refunds`, `limit`, `offset` |
| GET | `/api/v1/payments/{id}` | Bearer (tenant-scoped) | Get one |
| POST | `/api/v1/payments/{id}/refund` | owner+ | Body: `{amount_cents?, reason?}`. Defaults to full refund. |
| GET | `/api/v1/members/{id}/payments` | Bearer (tenant-scoped) | Convenience — payments for one member, newest first |
| GET | `/api/v1/dashboard/revenue` | Bearer (tenant-scoped) | Summary: this-month, last-month, MoM%, by-plan, by-method, ARPM |

`staff+` = staff, sales, owner, super_admin (matches the existing
Subscription contract).

`owner+` = owner, super_admin. Refund is owner-gated.

No `PATCH /payments/{id}` and no `DELETE /payments/{id}` — append-only
is enforced at the API surface, not just at the service.

### Schemas

**`RecordPaymentRequest`**
```json
{
  "member_id": "...",
  "amount_cents": 25000,
  "payment_method": "cash",
  "paid_at": "2026-04-29",
  "subscription_id": "...",
  "notes": "April monthly fee"
}
```

`amount_cents` must be `> 0`. Refunds have their own endpoint.

**`RefundPaymentRequest`**
```json
{ "amount_cents": 10000, "reason": "partial refund — class cancelled" }
```

`amount_cents` is positive in the request (the system flips the sign
when writing the row). Omit for full refund.

**`PaymentResponse`** — full entity row.

**`RevenueSummaryResponse`**
```json
{
  "this_month": { "from": "...", "to": "...", "cents": 1840000 },
  "last_month": { "from": "...", "to": "...", "cents": 1640000 },
  "mom_pct": 12.2,
  "by_plan": [{ "plan_id": "...", "plan_name": "Monthly", "cents": 1420000 }],
  "by_method": { "cash": 740000, "credit_card": 1100000 },
  "arpm_cents": 18400,
  "currency": "ILS"
}
```

---

## Frontend

### Feature folder

```
features/payments/
├── api.ts                   # 6 endpoint wrappers
├── hooks.ts                 # TanStack Query hooks
├── types.ts                 # re-exports from api-types
├── PaymentsPage.tsx         # /payments — table view
├── PaymentRow.tsx           # one row in the table
├── RecordPaymentDialog.tsx  # the "+ Record Payment" form
├── RefundPaymentDialog.tsx  # owner-only refund flow
├── PaymentsSection.tsx      # used on the member detail page
└── *.test.tsx
```

### Layout sketch — `/payments`

```
┌─ PageHeader: "תשלומים" ─────────────────────────────────────────────┐
│  [+ רישום תשלום]   [חיפוש: ...]   [תקופה: החודש ▼]   [שיטה: הכל ▼]   │
└──────────────────────────────────────────────────────────────────────┘

┌─ Net revenue this month: 18,400 ₪ ──────────────────────────────────┐
│  vs 16,400 last month (+12%)                                          │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────┬───────────┬─────────┬─────────┬──────┬─────────────────┐
│ תאריך       │ מנוי      │ סכום    │ שיטה    │ מסלול │ פעולות          │
├─────────────┼───────────┼─────────┼─────────┼──────┼─────────────────┤
│ 29/4/2026   │ Yael C.   │ 250 ₪   │ מזומן   │ חודשי │ ⋮ (refund)      │
│ 28/4/2026   │ Maya B.   │ 100 ₪   │ אשראי   │ חודשי │ ⋮               │
│ 22/4/2026   │ Yael C.   │ -50 ₪ 🔻│ —       │ —     │ refund of 250₪  │
└─────────────┴───────────┴─────────┴─────────┴──────┴─────────────────┘
```

- Refund rows render with a 🔻 indicator and link back to the original.
- Click a row → optional drawer showing notes / metadata.
- Top "Net revenue this month" widget reuses the same data as the
  dashboard.

### Layout sketch — Member detail "Payments" section

```
┌─ תשלומים ────────────────────────────────────────[+ רישום תשלום]──┐
│                                                                    │
│  סה"כ ששולם: 1,250 ₪    החזרים: -50 ₪    נטו: 1,200 ₪              │
│                                                                    │
│  29/4/2026   250 ₪   מזומן   חודשי                       ⋮         │
│  29/3/2026   250 ₪   מזומן   חודשי                       ⋮         │
│  29/2/2026   250 ₪   מזומן   חודשי                       ⋮         │
│  29/1/2026   250 ₪   מזומן   חודשי                       ⋮         │
│  29/12/2025  300 ₪   מזומן   רישום + חודש ראשון           ⋮         │
│  29/12/2025  -50 ₪🔻 —       refund: כפילות               ⋮         │
└────────────────────────────────────────────────────────────────────┘
```

The **"+ רישום תשלום"** button is the prominent placement that makes
the walk-in flow fast: enroll → click button → dialog pre-fills plan
price + cash + today → save. Two clicks for the common case.

### `RecordPaymentDialog`

Auto-fills (when triggered from a member with an active sub):
- Member: pre-set, read-only
- Subscription: dropdown (the active one, plus historical for
  backdated entries); optional ("Drop-in / one-off" choice for null)
- Amount: defaults to `sub.price_cents` if a sub is selected
- Method: defaults to `sub.payment_method` (or `cash` for drop-ins)
- Paid at: today
- Notes: empty

User just confirms + submits. The dialog also exposes a "Backdate"
toggle that allows `paid_at` more than 30 days ago (small friction
against accidental typos).

### `RefundPaymentDialog`

Owner+ only — the menu option doesn't render for staff.

- Original amount: read-only display
- Already refunded: read-only display (cumulative)
- Refund amount: defaults to the **remaining refundable amount**
- Reason: required text input

Submit → calls `POST /payments/{id}/refund` → on success, reloads
the member's payment list.

### Permissions

```ts
// permissions.ts
export type Feature =
  | ...
  | "payments"   // already in BASELINE — Payments is BASIC, not gated
  | ...
```

`payments` is **NOT** added to `GATED_FEATURES`. It's already in the
`BASELINE` for owner. Add it to staff + sales baselines so they can
record payments. Coach stays blocked.

### Dashboard wire-up

Every "בקרוב" placeholder on `GymDashboard.tsx` flips to a real
number from `GET /api/v1/dashboard/revenue`:

- "הכנסות החודש" (Revenue this month) → `summary.this_month.cents`
- "שינוי חודשי" (MoM change) → `summary.mom_pct`
- "הכנסות לפי מסלול" (Revenue per plan) → small bar chart from
  `summary.by_plan`
- "הכנסה ממוצעת למנוי" (ARPM) → `summary.arpm_cents`

Super_admin "Total platform revenue" widget runs the same query
across every active tenant and sums.

### Error humanizer

`humanizePaymentError` in `lib/api-errors.ts`:

- 403 → "אין לכם הרשאה לרשום תשלום"
- 404 → "התשלום לא נמצא"
- 409 `PAYMENT_REFUND_EXCEEDS_ORIGINAL` → "סכום ההחזר גדול מהיתרה
  הניתנת להחזר"
- 409 `PAYMENT_ALREADY_FULLY_REFUNDED` → "התשלום כבר הוחזר במלואו"
- 422 → "הפרטים שהוזנו אינם תקינים"

---

## Observability

Structlog events:

| Event | Fields | When |
|---|---|---|
| `payment.recorded` | tenant_id, payment_id, member_id, subscription_id?, amount_cents, method, paid_at | POST /payments success |
| `payment.refunded` | tenant_id, payment_id, original_payment_id, amount_cents (negative), reason?, by | POST /payments/{id}/refund success |
| `payment.refund_blocked` | tenant_id, payment_id, reason (`exceeds`/`fully_refunded`) | Refund attempt rejected |

CloudWatch Logs Insights queries (prod) for the support team:
"all payments today across the platform" + "all refunds this month".

---

## Tests

### Backend

| Type | File | Coverage |
|---|---|---|
| Unit | `test_payment_entity.py` | `is_refund()`; signed-amount semantics; required fields |
| Unit | `test_payment_service.py` | mocked repo — tenant scoping; permission gates; refund math (full + partial + over-cap + already-fully-refunded); cross-resource validation (member tenant, sub tenant + sub.member_id match); `paid_at` future rejection; backdate flag |
| Integration | `test_payment_repo.py` | CRUD; tenant isolation; range sums (`sum_for_range`); sum-by-plan; refund chain reads; cumulative-refunded math against real DB |
| E2E | `test_payments.py` | full HTTP — record, list, get one, refund, partial refund, refund-exceeds rejected, dashboard `/revenue` summary; permissions per role; member-scoped list endpoint; cannot DELETE/PATCH a payment via API |
| E2E | `test_cross_tenant_isolation.py` (additions) | ~6 probes for payments + refund + dashboard summary |
| E2E | `test_payments_dashboard.py` | /dashboard/revenue: zero state; this-month vs last-month; MoM%; by-plan grouping; by-method grouping; ARPM; refund subtracts from totals |

Target: **~35 new backend tests**.

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | Each wrapper hits the right URL + body shape |
| `RecordPaymentDialog.test.tsx` | Auto-fills from active sub; submits null sub_id for drop-in; validation rejects amount=0; backdate toggle exposes >30d picker |
| `RefundPaymentDialog.test.tsx` | Defaults to remaining refundable; validation rejects > remaining; reason required |
| `PaymentsPage.test.tsx` | Table renders; filter by date range; refund row badge |
| `PaymentsSection.test.tsx` (member detail) | Renders payment list; "+ Record Payment" button visible for staff+; hidden for coach |
| `lib/api-errors.test.ts` (additions) | `humanizePaymentError` for each branch |

Target: **~20 new frontend tests**.

---

## V1 → future migration path

- **Stripe / Israeli credit clearing.** When Phase 5 ships, `external_ref`
  becomes `external_provider` + `external_id`. Webhook handler converts
  successful charges into `POST /payments` calls (same code path as
  manual entry). Refunds via processor → call our refund endpoint →
  one path to write.
- **CSV import of historical payments.** New endpoint
  `POST /payments/import` accepts a CSV with the standard payment
  shape. Validates per-row, writes in batches of 500, returns a
  per-row report (success / which row failed / why).
- **Receipts.** Generate a PDF receipt from a payment row. Optional
  Israeli VAT receipt (חשבונית מס) if the gym is registered. Big
  surface — defer.
- **Payment plans / installments.** Member pays 1200₪ over 6 months
  (no monthly auto-charge). Currently modeled as 6 separate payment
  rows; a "payment plan" feature would group them and surface
  upcoming-due notifications.
- **Outstanding-balance widget.** Members whose subscription has
  expired but who haven't paid the renewal yet. Computed query, no
  schema change.

---

## Open questions (to revisit during implementation)

1. **Subscription auto-link vs manual link.** When recording a
   payment for a member with one active sub, do we auto-set
   `subscription_id` (and offer a "drop-in / unlinked" override) or
   force the user to pick? Leaning **auto-set** — fewer clicks for
   the 95% case; the override is one click away.
2. **Late-fee rows.** Recording a 50₪ late fee on top of the 250₪
   monthly — one row of 300₪, or two rows? Two is cleaner for
   reporting; one is faster to enter. v1: one row with a `notes`
   field, owner can break it out manually if their accountant cares.
3. **Tax / VAT.** Out of scope for v1 — every gym handles VAT
   differently (some are exempt, some charge separately). Future
   feature: optional `tax_cents` column + per-tenant tax rate.
4. **Drop-in price catalog.** Currently a drop-in payment is just an
   amount typed manually. A small "drop-in prices" table per tenant
   would let the dialog auto-suggest "yoga drop-in = 60₪". Defer
   until owners actually ask.
5. **Refund-of-refund?** Can you refund a refund row? The
   `refund_of_payment_id` chain technically allows it; v1 service
   blocks it (refund row's `refund_of_payment_id` must point at a
   non-refund row). Cleaner audit story.

---

## Migration plan

Single combined PR — backend + frontend + dashboard wire-up.
Estimate: **2 days** (smaller than Leads — no Kanban, no autocomplete,
no atomic multi-table transaction; bigger than a typical CRUD because
of the dashboard summary endpoint + refund math + cross-feature
member-detail-page integration).

**Backend:**

1. Migration `0014` — `payments` table + indexes + CHECK constraints.
2. Domain entity + 4 new exceptions + error-handler mapping.
3. `PaymentRepository` (CRUD + range sums + refund chain).
4. `PaymentService` — record, refund, summary, list filters.
5. Routes + schemas — 6 endpoints.
6. Dashboard `/revenue` endpoint — separate router or extend an
   existing `dashboard` router (TBD during implementation).
7. E2E tests including cross-tenant probes + dashboard summary tests.

**Frontend:**

1. Feature folder, types, api, hooks.
2. `/payments` page + `RecordPaymentDialog` + `RefundPaymentDialog`.
3. Member detail page: `PaymentsSection` integrated next to the
   subscription block.
4. Dashboard widget swap-out: remove `בקרוב` placeholders, render
   real numbers.
5. Permissions: `payments` baseline added for staff/sales (already in
   owner baseline); coach blocked.
6. Tests.

**Docs / spec:**

1. `docs/spec.md` §3.7 — replace with a one-paragraph pointer to
   this doc.
2. `docs/features/payments.md` — this doc, authoritative.
3. `docs/crm_logic.md` — append a "Payments are append-only; refunds
   are negative-amount rows" rule under §10.

---

## Related docs

- [`spec.md`](../spec.md) §3.7 — product overview of payments
- [`crm_logic.md`](../crm_logic.md) §9 (money / cents / one currency
  per tenant) + §10 (immutability rules — payments fall under this)
- [`subscriptions.md`](./subscriptions.md) — sibling entity; payment
  rows reference subscriptions
- [`members.md`](./members.md) — payment rows always reference a
  member; member detail page hosts the Payments section
- [`leads.md`](./leads.md) — convert flow creates a sub but **not** a
  payment; the operator records the payment after collecting it
