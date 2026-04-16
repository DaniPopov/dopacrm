# Feature: Membership Plans

> **Status:** Planned. Not yet implemented. Plan for review.
>
> **Order:** Build AFTER Members. BEFORE Subscriptions (they FK into plans).
>
> **Naming:** "Membership Plans" is what the gym SELLS to its members
> ("Monthly Unlimited", "10-class punch pack"). Don't confuse with
> [`saas-plans.md`](./saas-plans.md) — that's what the gym pays *DopaCRM*.

---

## Summary

A Membership Plan is a **product the gym sells**. Each gym defines its own plans: "Monthly Unlimited — 250 ILS", "10-class punch pack — 300 ILS", "Annual Student Discount — 2400 ILS", "Drop-in — 40 ILS". Plans are per-tenant (each gym has its own catalog) and owner-configurable.

Plans don't track who's subscribed — that's the Subscriptions feature next. Plans are the **catalog**; Subscriptions are the **assignments**.

---

## Why is this a separate feature and not just a column on Member?

This is the right question to ask. The obvious lazy design is `members.plan_name` + `members.price` — and it's wrong for five reasons:

### 1. The same plan is sold to many members

"Monthly Unlimited — 250 ILS" is ONE thing the gym sells to 80 customers. If it lives on Member, you're duplicating that exact string and price 80 times. When the owner renames it to "Gold Pass" or raises the price, you'd need to touch 80 rows — and any typo creates a "split" plan that doesn't really exist.

With a separate `membership_plans` table: one row, 80 members reference it.

### 2. Plans change, but history must stay stable

The owner bumps the price of "Gold Pass" from 250 to 300 ILS in May. What happens to members who signed up in April at the old price? If the price is a column on Member, you've just unknowingly raised everyone's rate. Ugly.

The proper design: the plan changes freely, but each Subscription **snapshots the price** at sign-up time (per the spec, `subscriptions.price_cents` is locked). That snapshot needs a real table for the plan to live in and a real reference from the subscription.

### 3. Members change plans over time

Today Dana is on Monthly Unlimited. Next month she switches to 10-class pack. Next year she upgrades to Premium Annual. If Plan lives on Member you LOSE this history when you overwrite the column. Revenue reporting dies — "what percentage of our Monthly Unlimited members churn to 10-class pack?" becomes unanswerable.

Plans + Subscriptions = temporal history. You can ask "what plan was Dana on in March 2026?".

### 4. Plans have structure, not just a name

- `type`: recurring vs one-time
- `billing_period`: monthly / quarterly / yearly
- `duration_days`: only meaningful for one-time plans (30-day trial pass)
- `is_active`: owner stops selling it but existing members keep using it
- `custom_attrs` JSONB: "includes 2 PT sessions", "valid Mon/Wed/Fri only", "1 guest pass"

None of that fits as a single column. You either balloon Member into 15+ plan-related columns (mostly null for each row), or you admit it's its own entity.

### 5. The dashboard asks questions that need GROUP BY plan

- "Revenue per plan this month"
- "Which plan has the highest churn?"
- "Are we selling more punch cards or monthly passes?"

These queries are straightforward when Plans is a real table (`GROUP BY plan_id`). They're painful or impossible with denormalized plan-name-on-member.

### The "gym can customize it" part — yes, that too

You're right that owner-configurability is part of the story. Each gym defines their own catalog — DopaCRM never hardcodes "Monthly Unlimited" as a built-in option. But the 5 reasons above are independent of customization: even if every gym had the same fixed plans, the structural reasons (history, price changes, GROUP BY) still force Plans into its own table.

Customization just makes it even more essential.

---

## Where this sits in Phase 2

```
  Phase 2 build order
  ────────────────────
  Members        ✅ shipped
  Membership Plans          ← THIS DOC (next)
  Subscriptions             ← needs Plans + Members
  Payments                  ← needs Subscriptions
  Leads                     ← independent, can ship anytime
```

Plans must land before Subscriptions because `subscriptions.plan_id` FKs into `membership_plans.id`. Plans is the dependency, Subscriptions is the consumer.

---

## User stories

1. **As an owner**, I create the plans my gym sells. Name, price, type, billing period, optional custom attributes.
2. **As an owner**, I edit a plan — typo in the name, price change, add a description.
3. **As an owner**, I deactivate a plan I no longer offer. Existing subscriptions stay active; new subscriptions can't pick it.
4. **As owner / staff**, I see the list of plans in the gym's catalog with counts of how many members are on each.
5. **As an owner**, I see on the dashboard how much revenue each plan generated this month. *(Arrives with Subscriptions + Payments — the Plans backend just makes it possible.)*

**Explicitly NOT in this feature:**
- Assigning a member to a plan → Subscriptions feature
- Recording a payment → Payments feature
- Class restrictions (which classes does this plan grant access to?) → Classes feature
- Discount codes / promotions → deferred to v2

---

## API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/plans` | Bearer (tenant-scoped) | List active plans in the caller's gym (filter `?include_inactive=true` for owner) |
| POST | `/api/v1/plans` | owner | Create a plan |
| GET | `/api/v1/plans/{id}` | Bearer (tenant-scoped) | Get one plan |
| PATCH | `/api/v1/plans/{id}` | owner | Update (partial) |
| POST | `/api/v1/plans/{id}/deactivate` | owner | Soft-disable for new subscriptions |
| POST | `/api/v1/plans/{id}/activate` | owner | Re-enable |

**Why no `DELETE`?** Same reasoning as Members: existing Subscriptions FK into the plan. Hard-delete would orphan them or wipe history. Deactivate is the soft-delete.

**Why owner-only for mutations?** Plans define pricing — commercial decisions. Staff and sales can READ the catalog (needed to enroll a new member into a plan) but can't change it. Matches the spec's "owner handles config, pricing" principle.

---

## Domain (Layer 3)

**`domain/entities/membership_plan.py`**

```python
class PlanType(StrEnum):
    RECURRING = "recurring"   # billed every billing_period until cancelled
    ONE_TIME = "one_time"     # single charge, optional duration_days

class BillingPeriod(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ONE_TIME = "one_time"     # used for PlanType.ONE_TIME

class MembershipPlan(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str                         # "Monthly Unlimited"
    description: str | None
    type: PlanType
    price_cents: int                  # stored in cents, currency from tenant
    currency: str                     # inherited from tenant at create time
    billing_period: BillingPeriod
    duration_days: int | None         # only for one_time plans
    is_active: bool
    custom_attrs: dict[str, Any]      # "includes_pt_sessions": 2, "valid_days": [...]
    created_at: datetime
    updated_at: datetime

    def can_subscribe(self) -> bool:
        """Returns true if new Subscriptions may reference this plan."""
        return self.is_active
```

**Exceptions:**
- `MembershipPlanNotFoundError` → 404
- `MembershipPlanInUseError` → 409 (someone tries hard-delete instead of deactivate — unlikely but protects against future code)
- `InvalidPlanShapeError` → 422 (e.g., one_time plan without duration_days, or duration_days on a recurring plan)

---

## Data Model

**`membership_plans` table**

```sql
CREATE TABLE membership_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  type TEXT NOT NULL CHECK (type IN ('recurring', 'one_time')),
  price_cents INT NOT NULL CHECK (price_cents >= 0),
  currency TEXT NOT NULL,
  billing_period TEXT NOT NULL CHECK (
    billing_period IN ('monthly', 'quarterly', 'yearly', 'one_time')
  ),
  duration_days INT CHECK (duration_days IS NULL OR duration_days > 0),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  custom_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Shape integrity: one_time plans MUST have duration_days; recurring ones MUST NOT
  CHECK (
    (type = 'recurring' AND duration_days IS NULL AND billing_period <> 'one_time')
    OR (type = 'one_time' AND duration_days IS NOT NULL AND billing_period = 'one_time')
  ),

  -- Name unique within tenant (prevents duplicate "Monthly Unlimited" rows)
  UNIQUE (tenant_id, name)
);

CREATE INDEX idx_plans_tenant_active ON membership_plans(tenant_id, is_active);
```

**Design choices:**
- `tenant_id ON DELETE CASCADE` — nuking a tenant nukes its plans (we don't hard-delete tenants but the FK stays honest).
- Check constraint on `(type, duration_days, billing_period)` — prevents the "one_time plan with no expiry" bug from reaching prod.
- `UNIQUE (tenant_id, name)` — inside one gym you can't have two plans called "Gold" ; across gyms you can.
- `currency` is stored, not inherited at read-time, because once the plan is created it's locked — changing the tenant's currency later shouldn't quietly change the plan price interpretation.

---

## Service (Layer 2)

`services/membership_plan_service.py`:

```python
class MembershipPlanService:
    async def create(self, caller, data) -> MembershipPlan: ...
    async def update(self, caller, plan_id, **fields) -> MembershipPlan: ...
    async def deactivate(self, caller, plan_id) -> MembershipPlan: ...
    async def activate(self, caller, plan_id) -> MembershipPlan: ...
    async def get(self, caller, plan_id) -> MembershipPlan: ...
    async def list_for_tenant(
        self, caller, *, include_inactive: bool = False
    ) -> list[MembershipPlan]: ...
```

**Business rules enforced here:**
- Tenant scoping on every method (same pattern as MemberService).
- `create`/`update`/`deactivate`/`activate` — owner or super_admin only.
- `list`/`get` — any tenant user (staff/sales need to know the catalog to enroll members).
- On create: `currency` defaults to the tenant's currency if not provided.
- On create/update: validate plan shape (one_time needs duration_days, recurring doesn't — redundant with DB check but gives a nicer error).
- Name uniqueness within tenant enforced by DB UNIQUE → 409 mapped by error handler.

---

## Frontend

### Feature folder

```
features/plans/
├── api.ts              # list, get, create, update, activate, deactivate
├── hooks.ts            # TanStack Query wrappers with invalidation
├── types.ts            # re-exports from api-types
├── PlanForm.tsx        # shared create/edit form
├── PlanListPage.tsx    # /plans — list + inline create + row actions
├── PlanDetailPage.tsx  # /plans/:id — edit page, mirrors Tenant/Member pattern
└── *.test.tsx          # full coverage (same bar as Members)
```

### Routing + permissions

```tsx
// permissions.ts — "plans" already in the Feature union
// Add to BASELINE:
//   owner: [..., "plans"]  (already there)
//   staff: [..., "plans"]  (read-only on frontend, owner-only on backend = fine)
//   sales: [..., "plans"]  (same — need to see catalog when enrolling leads)

<Route element={<RequireFeature feature="plans" />}>
  <Route path="/plans" element={<PlanListPage />} />
  <Route path="/plans/:id" element={<PlanDetailPage />} />
</Route>
```

### Sidebar

Uncomment the plans entry that's already prepared in `NAV_ITEMS`.

### UI choices

- Table on desktop, cards on mobile (same responsive pattern Members + Tenants use).
- Status filter chips: All / Active / Inactive.
- "פעולות" row dropdown:
  - owner: עריכה, השבתה / הפעלה
  - staff / sales: view only (no dropdown OR show עריכה disabled with tooltip explaining owner-only)
- Plan form fields:
  - Required: name, type (radio: חוזר / חד-פעמי), price
  - Billing period (select): depends on type
  - Duration days: only shown when type = one_time
  - Description (textarea, optional)
  - `custom_attrs` — raw JSON textarea in v1 (same as Members custom_fields, proper UI lands with Owner Settings).

### Error humanizer

`humanizePlanError(err)` in `lib/api-errors.ts`:
- 404 → "התוכנית לא נמצאה"
- 409 duplicate name → "תוכנית בשם הזה כבר קיימת"
- 422 → "הפרטים שהוזנו אינם תקינים"

---

## Tests

### Backend

| Type | File | What |
|---|---|---|
| Unit | `test_membership_plan_entity.py` | `can_subscribe()`, shape integrity (one_time vs recurring), defaults |
| Integration | `test_membership_plan_repo.py` | CRUD, UNIQUE (tenant, name), cross-tenant isolation, is_active filter |
| E2E | `test_membership_plans.py` | Full HTTP: create as owner (201), create as staff (403), duplicate name (409), deactivate preserves existing subscriptions (verify via a seeded Subscription when that feature lands — skip assertion for now), invalid shape → 422 |

### Frontend

| File | Coverage |
|---|---|
| `api.test.ts` | Every function, URL, body, query string |
| `PlanListPage.test.tsx` | States, filters, row actions, navigation |
| `PlanForm.test.tsx` | Required fields, conditional duration_days, submit shape |
| `PlanDetailPage.test.tsx` | Loading, error, success → navigate |
| `api-errors.test.ts` | humanizePlanError for each status |
| `permissions.test.ts` | `"plans"` in owner/staff/sales baseline |

Target: **~25 new frontend + ~15 new backend** tests — same bar as Members.

---

## Decisions

1. **Separate table, not a column on Member.** See the top of this doc.
2. **Deactivate, not delete.** Preserves historical Subscriptions. Matches Members pattern.
3. **Name unique per tenant.** Prevents "Monthly" vs "Monthly " typo duplicates within one gym.
4. **Currency locked at creation.** Don't silently change a plan's interpretation when the tenant changes their currency.
5. **`custom_attrs` as JSONB, no UI in v1.** Backend accepts/returns unchanged. Consistent with members.custom_fields.
6. **Owner-only for mutations.** Commercial decisions. Staff/sales can READ.
7. **No discount/promo codes in this feature.** v2. Don't bundle growth features into the core catalog.
8. **No class-access restrictions.** Plans define WHAT IS SOLD, not WHAT IT UNLOCKS. Class-restricted plans are a Classes-feature concern.
9. **`price_cents >= 0` allowed.** A zero-price "free trial plan" is legitimate. Negative prices are not.
10. **Billing period is an enum, not arbitrary text.** Keeps the dashboard's "revenue per billing cadence" query sane.

---

## Open questions

1. **Trial plans** — "2-week free trial" is a common one-time plan with `price_cents=0, duration_days=14`. Any special handling, or just a normal one_time plan? → Probably just a normal plan. Owner can name it whatever.
2. **Prorated pricing** — if a member joins mid-month, do they pay a pro-rated amount? → Deferred. For v1 the owner handles proration manually via adjusted one-time payments when Payments lands.
3. **Plan hierarchies / tiers** — Silver / Gold / Platinum with "upgrade path" logic? → Deferred. For v1 each plan is independent.
4. **Multi-currency per plan** — same "Gold Pass" available at 250 ILS or 75 USD? → Deferred. Plan has one currency (tenant's). Address when first international customer asks.
5. **Should `description` support Markdown?** → No for v1. Plain text is safer for now.

---

## Migration plan

Single backend PR for Plans alone:
- Migration `0006_create_membership_plans.py`
- Domain entity + exceptions
- Repo + service
- Routes + schemas
- Tests (unit + integration + e2e)

Then single frontend PR:
- Feature folder with full CRUD
- Sidebar entry uncomment
- Permissions baselines updated
- Tests

Roughly matches the Members split we did: backend as `ec78bc6`, frontend as `212f2ae`. Total ~1-1.5 days.

---

## Related docs

- [`spec.md`](../spec.md) §3.5 — Membership Plans in the product spec
- [`members.md`](./members.md) — sibling entity, Subscriptions FK into both
- [`saas-plans.md`](./saas-plans.md) — DON'T CONFUSE. SaaS plans are what the gym pays DopaCRM.
- [`classes.md`](./classes.md) — adjacent but independent. Class passes are NOT membership plans.
- [`../skills/build-backend-feature.md`](../skills/build-backend-feature.md) — recipe we'll follow
- [`../skills/build-frontend-feature.md`](../skills/build-frontend-feature.md) — recipe we'll follow
