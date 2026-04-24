# Feature: Tenant Feature Flags

> **Status:** Planned. Spec for review — lands with the Schedule feature.
>
> **What this is:** a per-tenant on/off switch for **non-core features**.
> Lets super_admin decide which gyms see Coaches, Schedule, and (future)
> other advanced modules. Ungated "basic" features (Members, Classes,
> Plans, Subscriptions, Attendance) are always on for every tenant.

---

## Why this doc exists

DopaCRM's core thesis is **owner-configurable flexibility** (`docs/spec.md` §1).
Shipping Coaches + Schedule as always-on contradicts that: a solo-operator
boxing gym doesn't want payroll tracking, and a yoga studio without
recurring classes doesn't want a weekly calendar. Forcing the UI clutter
hurts the simple case.

This doc is the **minimum mechanism to turn features on and off per
gym**, without building the full Phase 4 dynamic-roles UI yet.

Think of it as the gateway drug to Phase 4 (owner self-service settings):
- Today: super_admin toggles.
- Tomorrow (v2): owner toggles via Settings page.
- Later: dynamic roles grant each feature per-role-per-tenant.

Same column, same `canAccess`, same call sites. Incremental unlock.

---

## Scope

### Gated features (today)

| Feature | Default for new tenants | Default for existing tenants |
|---|---|---|
| `coaches`  | OFF | ON (backfilled) |
| `schedule` | OFF | OFF (nothing to grandfather) |

### Ungated features (always on)

- `dashboard`, `tenants` (super_admin platform view), `members`,
  `classes`, `plans`, `attendance`, `users` (gym staff management),
  `leads` (when it ships), `payments` (when it ships).

Rule of thumb: **a feature is gated if the gym can plausibly operate
without it**. Members + Attendance + Plans are the CRM. Coaches,
Schedule, Leads-pipeline, Payments-reconciliation are value-adds.

---

## Data model

### Column on `tenants`

```sql
ALTER TABLE tenants
  ADD COLUMN features_enabled JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill existing tenants so nothing silently breaks.
UPDATE tenants SET features_enabled = '{"coaches": true}'::jsonb;
```

### Shape

```json
{
  "coaches":  true,
  "schedule": false
}
```

- Absent keys = OFF. We do NOT store `false` explicitly; missing = disabled.
- Unknown keys ignored (forward-compat when the UI doesn't know about a
  future feature yet).
- Value is always a boolean. No per-feature config piggy-backs on this
  column — when Schedule needs per-tenant config (e.g. "default
  materialization horizon"), it goes in a different column/table.

### Why JSONB and not discrete bool columns?

- Adding a new gated feature later = no migration.
- Single query to read "what's on for this tenant" = one column.
- Easy to log `before/after` diffs when super_admin flips flags.

**Tradeoff accepted:** Postgres can't type-check that the keys match
the list of known features. We enforce that in the service layer
(`is_feature_enabled` rejects unknown feature names) so a typo doesn't
silently enable nothing.

---

## Domain + service

### `app/core/feature_flags.py`

```python
from enum import StrEnum

class GatedFeature(StrEnum):
    COACHES  = "coaches"
    SCHEDULE = "schedule"

# Features listed here are checked against tenant.features_enabled.
# Everything NOT listed here is always on.
GATED = {GatedFeature.COACHES, GatedFeature.SCHEDULE}


def is_feature_enabled(tenant: Tenant, feature: str) -> bool:
    """Return True if the feature is ungated OR enabled for this tenant.

    Unknown feature strings → False (fail-closed).
    """
    if feature not in {f.value for f in GatedFeature}:
        # Ungated feature — always on (or unknown, which we treat as off).
        return feature in UNGATED_ALWAYS_ON
    return bool(tenant.features_enabled.get(feature))
```

### `FeatureDisabledError`

```python
class FeatureDisabledError(AppError):
    """Gated feature is off for this tenant. Returns HTTP 403."""

    def __init__(self, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is not enabled for this tenant",
            "FEATURE_DISABLED",
        )
```

Mapped in `error_handler.py` to **403 Forbidden**. The feature *exists*,
the caller is authenticated, but access is denied by tenant config —
the natural semantic for a gate.

### Service-layer guards

Every service method in a gated feature starts with:

```python
class CoachService:
    async def create_coach(self, *, caller, ...):
        tenant = await self._tenant_repo.find_by_id(_UUID(caller.tenant_id))
        if not is_feature_enabled(tenant, "coaches"):
            raise FeatureDisabledError("coaches")
        # ... rest of the method
```

A small decorator could DRY this, but the explicit guard line makes
the gate **visible in code review** — worth the repetition.

---

## API endpoints

### Toggle features (super_admin only)

```
PATCH /api/v1/tenants/{tenant_id}/features
Authorization: Bearer <super_admin token>
Content-Type: application/json

{ "coaches": true, "schedule": false }
```

- **Auth**: super_admin only. Owner-self-service ships in v2 as a
  one-line role-gate change.
- **Shape**: partial merge into `features_enabled`. Missing keys are
  left unchanged. Explicit `false` disables.
- **Validation**: unknown keys rejected (422) so a typo doesn't
  silently enable nothing.
- **Logging**: every toggle emits `tenant.features_changed` structlog
  event with `tenant_id`, `changed_by`, `before`, `after`, and
  `diff`. Owner audit trail.
- **Response**: the full updated `features_enabled` object.

### Reading (implicit on every /auth/me + /tenants/{id})

The `/auth/me` response (which the frontend hydrates into `auth-provider`)
grows `features_enabled: dict[str, bool]` so `canAccess` can consult
it locally without an extra round-trip.

The `/tenants/{id}` response also returns `features_enabled` so the
super_admin settings panel can render the current state.

---

## Frontend wiring

### `permissions.ts` evolves

```ts
const GATED_FEATURES = new Set<Feature>(["coaches", "schedule"])

export function canAccess(
  user: User | null | undefined,
  feature: Feature,
  overrides: TenantOverrides = EMPTY_OVERRIDES,
  tenantFeatures: Record<string, boolean> = {},
): boolean {
  if (!user) return false
  const baseline = BASELINE[user.role]

  // Gated features: tenant flag must be on regardless of baseline.
  if (GATED_FEATURES.has(feature) && !tenantFeatures[feature]) {
    return false
  }

  if (baseline.includes(feature)) return true
  // ... staff/sales override logic unchanged
}
```

Call sites stay the same — Sidebar, `<RequireFeature>`, route guards
all consume `canAccess(user, feature)` today. When the `tenantFeatures`
map comes from `auth-provider`, nothing else changes.

### Sidebar visibility

```
feature="coaches"  → hidden when tenant has coaches OFF
feature="schedule" → hidden when tenant has schedule OFF
```

### Route guards

`<RequireFeature feature="coaches" />` blocks the route component —
typing `/coaches` in the URL redirects to `/dashboard` if the flag
is off. Defense in depth alongside the backend's `FeatureDisabledError`.

### Super_admin toggle UI — on `/tenants/{id}`

New section titled **"תכונות"** (Features) with one checkbox per
gated feature:

```
┌── תכונות ──────────────────────────┐
│  ☑ מאמנים + חישוב שכר              │
│  ☐ לוח שיעורים שבועי                │
│                                     │
│  [שמירה]                            │
└─────────────────────────────────────┘
```

Only super_admin sees this section. One checkbox per `GATED_FEATURES`
entry; save button posts `PATCH /tenants/{id}/features`.

---

## Observability

Single structlog event — the gate is stable once set:

| Event | Fields | When |
|---|---|---|
| `tenant.features_changed` | tenant_id, changed_by, before, after, diff | Super_admin flips a flag |

Loki query to audit all feature changes across the platform:

```
{app="dopacrm"} |= "tenant.features_changed"
  | line_format "{{.changed_by}} → {{.tenant_id}}: {{.diff}}"
```

No per-call log for `is_feature_enabled` — it's a hot-path function
called on every gated request. The 403 already surfaces in the access
log via the global middleware.

---

## Tests

### Backend

| Type | File | Coverage |
|---|---|---|
| Unit | `test_feature_flags.py` | `is_feature_enabled` — ungated always true, gated with key missing = false, gated with key=false = false, gated with key=true = true, unknown feature name = false |
| Unit | `test_tenant_entity.py` (+additions) | `Tenant.features_enabled` default empty, JSONB round-trip |
| Integration | `test_tenant_repo.py` (+additions) | PATCH merges partial keys, leaves unlisted keys untouched |
| E2E | `test_tenant_features.py` | super_admin can toggle, owner cannot (403), invalid feature name (422), toggling off a feature → existing endpoint returns 403 immediately |
| E2E | `test_cross_tenant_isolation.py` (+additions) | A's super_admin cannot flip B's features... wait, super_admin CAN — that's their job. So no cross-tenant probe here. Instead: A's owner cannot flip A's features (owner-not-authorized test). |

### Frontend

| File | Coverage |
|---|---|
| `permissions.test.ts` (+additions) | `canAccess("coaches", ..., {coaches: false})` returns false even for owner; `canAccess("coaches", ..., {coaches: true})` honors baseline |
| `TenantFeaturesSection.test.tsx` | Checkbox state reflects prop, save triggers PATCH, only visible to super_admin |

---

## Migration plan (applied in the same PR as Schedule)

1. **Migration 0012:** `tenants.features_enabled` JSONB + backfill
   `{"coaches": true}` for existing rows.
2. **`app/core/feature_flags.py`** + `is_feature_enabled` helper +
   `FeatureDisabledError` + error_handler entry.
3. **`CoachService`** — add gate check at the top of every mutation.
   Read methods stay ungated (so a disabled tenant's historical
   coach data is still visible during rollback, though invisible via
   sidebar).

   Wait — actually that's wrong. If Coaches is disabled, the sidebar
   hides it and the route redirects. A gym that had Coaches on, then
   turned it off, should not see the menu item. Historical data
   behind the scenes: that's an owner-decision at re-enable time.
   So the gate applies at **both reads and writes** for simplicity.

4. **`/auth/me` + `/tenants/{id}`** include `features_enabled` in the
   response.
5. **`PATCH /api/v1/tenants/{id}/features`** + route + schema.
6. **Frontend:**
   - `auth-provider` threads `features_enabled` into React context.
   - `canAccess` updated.
   - Sidebar + `<RequireFeature>` call sites unchanged.
   - New `TenantFeaturesSection` component on `/tenants/{id}`.

---

## Future work (not in this PR)

- **Owner self-service.** When the Settings page lands, owners get
  the same toggle UI (behind `canAccess(user, "settings")`). The
  endpoint becomes owner+ instead of super_admin-only — one line of
  code.
- **Dynamic roles** (Phase 4, `docs/features/roles.md`). Replaces
  the `BASELINE` map with tenant-scoped grants. `features_enabled`
  stays as the tenant-level gate; roles become the per-user grant.
- **Per-feature config.** E.g. "Schedule uses a 12-week horizon
  instead of 8 for this gym." Lives in a separate
  `tenants.feature_configs JSONB` column if it ever materializes.
  Don't overload `features_enabled`.
- **Audit trail surface.** Owner dashboard panel: "Last 10 feature
  changes." Reads from structlog events. Future feature.
- **Feature deprecation flow.** When we retire a gated feature, we
  need a migration that removes the key from every
  `features_enabled` row + a frontend removal. Standard column
  hygiene — no special handling.

---

## Related

- [`coaches.md`](./coaches.md) — first gated feature
- [`schedule.md`](./schedule.md) — second gated feature, shipping
  alongside this mechanism
- [`roles.md`](./roles.md) — the Phase 4 dynamic roles spec that
  builds on top of this gate
- [`../crm_logic.md`](../crm_logic.md) §12 permission layering —
  `is_feature_enabled` slots in as layer 2.5 (between role gate and
  tenant scope)
