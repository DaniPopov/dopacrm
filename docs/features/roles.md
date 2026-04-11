# Feature: Dynamic Roles

> **Status:** Planned. Not yet implemented. Spec only.
>
> **Why deferred:** Building the permission grid before real gym-scoped features exist means designing in the dark. Revisit once Members, Membership Plans, Subscriptions, Payments, and Leads have landed — then we have something concrete to configure per-role.
>
> **Tracking:** `TODO.md` → "Features — Flexibility"

---

## Summary

Today, `users.role` is a text column holding one of four literals: `super_admin`, `owner`, `staff`, `sales`. This is a temporary shape.

The real model is **dynamic, per-tenant, owner-configurable roles**. Only `super_admin` and `owner` are system-defined. Every other role is a row in a `tenant_roles` table that the owner creates, names, and assigns feature grants to.

**Why this matters:** DopaCRM's core differentiator is owner-level flexibility (see `docs/specs.md` §1). A gym with a front-desk cashier, two trainers, and a separate sales consultant should be able to model that — not pick from three fixed buckets. Rigid role enums force the gym to bend to the software.

**Example outcomes:**
- "Dana's Gym" keeps the seeded `Staff` role but renames it to `Reception`.
- "Iron Palace" deletes `Sales` and creates `Trainer` (members only), `Night Manager` (everything except billing), and `Cashier` (payments + members).
- "CrossFit TLV" keeps defaults unchanged — they're a 2-person shop.

---

## User stories

1. **As an owner**, I can see all roles in my gym and what features each role can access.
2. **As an owner**, I can create a new custom role with a name and a checkbox grid of grantable features.
3. **As an owner**, I can rename or delete a custom role. System roles (`owner`, `super_admin`) are read-only.
4. **As an owner**, I can reassign users to a different role. Deleting a role is blocked if users are still assigned to it.
5. **As a staff/custom-role user**, I see only the features my role grants, in both the sidebar and as route-level guards.
6. **As a super_admin**, I am unaffected by tenant roles — I always see platform features.

---

## Data model

### PostgreSQL: `tenant_roles` table

```sql
CREATE TABLE tenant_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  features TEXT[] NOT NULL DEFAULT '{}',
  is_system BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name),
  CHECK (
    -- System roles must be platform-level or one per tenant
    (is_system = FALSE)
    OR (name IN ('super_admin', 'owner'))
  )
);

CREATE INDEX idx_tenant_roles_tenant ON tenant_roles(tenant_id);
```

**Semantics:**
- `tenant_id IS NULL` means platform-level. Only `super_admin` lives here.
- `is_system = TRUE` means the owner cannot rename, delete, or change the feature list. `super_admin` and `owner` are the only system roles.
- `features` is a Postgres array of feature slugs (`['dashboard', 'members', 'payments']`). Slugs come from the `Feature` union in `frontend/src/features/auth/permissions.ts` — keep them in sync.

### PostgreSQL: `users.role` → `users.role_id`

```sql
-- Migration adds role_id and backfills from existing role text column
ALTER TABLE users ADD COLUMN role_id UUID REFERENCES tenant_roles(id);

-- Backfill: for each user, find the matching tenant_role by name
UPDATE users u
SET role_id = r.id
FROM tenant_roles r
WHERE r.tenant_id = u.tenant_id AND r.name = u.role;

-- super_admin users get the platform-level role
UPDATE users u
SET role_id = r.id
FROM tenant_roles r
WHERE r.tenant_id IS NULL AND r.name = 'super_admin' AND u.role = 'super_admin';

ALTER TABLE users ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE users DROP COLUMN role;
```

### Seed data (on tenant creation)

When a new tenant is created, `TenantService.create()` also inserts:

| Name | is_system | features |
|---|---|---|
| `Owner` | true | all gym features (`members`, `plans`, `leads`, `payments`, `reports`, `settings`) |
| `Staff` | false | `dashboard`, `members`, `payments` |
| `Sales` | false | `dashboard`, `leads`, `members` |

The `super_admin` role is seeded once at platform bootstrap (tenant_id = NULL, is_system = true).

---

## API (Layer 1)

All role management is owner-scoped — `super_admin` does not manage per-tenant roles (they are gym-owner business).

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/roles` | Bearer | List roles for current tenant (sidebar + user form dropdown) |
| POST | `/api/v1/roles` | owner | Create a custom role |
| GET | `/api/v1/roles/{id}` | Bearer | Get role by id |
| PATCH | `/api/v1/roles/{id}` | owner | Rename / update features. System roles reject. |
| DELETE | `/api/v1/roles/{id}` | owner | Delete custom role. 409 if users still assigned. System roles reject. |

And `/auth/me` changes shape:

**Before:**
```json
{ "id": "...", "email": "...", "role": "staff" }
```

**After:**
```json
{
  "id": "...",
  "email": "...",
  "role": {
    "id": "...",
    "name": "Receptionist",
    "features": ["dashboard", "members", "payments"],
    "is_system": false
  }
}
```

### Error mapping

| Exception | HTTP | Scenario |
|---|---|---|
| `RoleNotFoundError` | 404 | GET/PATCH/DELETE with unknown id |
| `RoleAlreadyExistsError` | 409 | POST/PATCH with duplicate name for tenant |
| `SystemRoleImmutableError` | 403 | PATCH/DELETE on `is_system = true` role |
| `RoleInUseError` | 409 | DELETE on role with assigned users |
| `InvalidFeatureError` | 422 | POST/PATCH with feature slug not in allow-list |
| `InsufficientPermissionsError` | 403 | Non-owner trying to manage roles |

---

## Service (Layer 2)

**`services/role_service.py`** — owner-scoped operations.

```python
class RoleService:
    async def list_for_tenant(self, tenant_id: UUID, actor: User) -> list[Role]: ...
    async def create(self, tenant_id: UUID, data: RoleCreate, actor: User) -> Role: ...
    async def update(self, role_id: UUID, data: RoleUpdate, actor: User) -> Role: ...
    async def delete(self, role_id: UUID, actor: User) -> None: ...

    async def seed_defaults_for_tenant(self, tenant_id: UUID) -> None:
        """Called from TenantService.create — not a public API."""
```

**Business rules (enforced in service, not routes):**
- Only `owner` (or `super_admin` impersonating) can mutate roles.
- System roles reject all mutations.
- Deletion requires zero assigned users.
- Feature slugs must be in the `GRANTABLE_FEATURES` allow-list (backend mirrors frontend `permissions.ts`).
- Role names are unique per tenant (enforced by DB UNIQUE + 409 mapping).

---

## Domain (Layer 3)

**`domain/entities/role.py`**

```python
class Role(BaseModel):
    id: UUID
    tenant_id: UUID | None  # None = platform-level (super_admin only)
    name: str
    features: list[str]
    is_system: bool
    created_at: datetime
    updated_at: datetime

    def can_access(self, feature: str) -> bool:
        return feature in self.features

    def is_mutable(self) -> bool:
        return not self.is_system
```

**`domain/exceptions.py`** — add:
- `RoleNotFoundError(AppError)`
- `RoleAlreadyExistsError(AppError)`
- `SystemRoleImmutableError(AppError)`
- `RoleInUseError(AppError)`
- `InvalidFeatureError(AppError)`

---

## Adapters (Layer 4)

**`adapters/storage/postgres/role/`** — standard repo pattern.

- `models.py` — `TenantRoleORM` (mirrors table)
- `repositories.py` — `RoleRepository` with `find_by_id`, `find_by_tenant`, `find_by_name`, `create`, `update`, `delete`, `count_users`

---

## Frontend

### types (`features/auth/types.ts`)

```ts
export interface Role {
  id: string
  tenant_id: string | null
  name: string
  features: Feature[]
  is_system: boolean
}

export interface User {
  id: string
  email: string
  role: Role  // <— was: Role union string
  tenant_id: string | null
  // ...
}
```

### permissions module (`features/auth/permissions.ts`)

The hardcoded `BASELINE` dict and `TenantOverrides` concept disappear. `canAccess` collapses to:

```ts
export function canAccess(user: User | null | undefined, feature: Feature): boolean {
  return user?.role.features.includes(feature) ?? false
}

export function accessibleFeatures(user: User | null | undefined): Feature[] {
  return user?.role.features ?? []
}
```

**Zero call-site changes.** `Sidebar.tsx`, `RequireFeature.tsx`, and every future component that already calls `canAccess(user, feature)` keeps working.

### New feature folder: `features/roles/`

Following the standard feature layout (see `docs/skills/build-frontend-feature.md`):

```
features/roles/
  api.ts          # listRoles, createRole, updateRole, deleteRole
  hooks.ts        # useRoles, useCreateRole, useUpdateRole, useDeleteRole
  types.ts        # Role, RoleCreate, RoleUpdate (mirrors backend schemas)
  RoleListPage.tsx     # /settings/roles — owner-only, grid of roles
  RoleForm.tsx         # Shared create/edit form with feature checkbox grid
  RoleListPage.test.tsx
```

### Route

```tsx
<Route element={<RequireFeature feature="settings" />}>
  <Route path="/settings/roles" element={<RoleListPage />} />
</Route>
```

### User form

The user create/edit form's "Role" dropdown currently uses a hardcoded list. It becomes:

```tsx
const { data: roles } = useRoles()
<Select>
  {roles?.map(r => <SelectItem value={r.id}>{r.name}</SelectItem>)}
</Select>
```

---

## Testing

### Backend

| Test | What |
|---|---|
| unit: `test_role_entity` | `Role.can_access()` matches feature list; `is_mutable()` is false for system |
| unit: `test_role_service` | seed_defaults creates Owner/Staff/Sales; delete blocks if users assigned; system role mutation raises |
| integration: `test_role_repository` | CRUD against real Postgres; UNIQUE constraint on (tenant_id, name) |
| e2e: `test_roles_api` | owner can CRUD, staff gets 403, deleting in-use role returns 409, renaming system role returns 403 |
| e2e: `test_tenant_create_seeds_roles` | new tenant has Owner/Staff/Sales after creation |
| migration: `test_role_migration_backfill` | existing users with `role='staff'` get `role_id` pointing to their tenant's Staff row |

### Frontend

| Test | What |
|---|---|
| unit: `permissions.test.ts` | rewritten — `canAccess(user, feature)` reads from `user.role.features` |
| unit: `RoleForm.test.tsx` | renders feature checkbox grid; validates name; system role disables editing |
| unit: `RoleListPage.test.tsx` | lists roles, opens create dialog, delete blocked for system roles |
| unit: `Sidebar.test.tsx` (new) | hides links based on `user.role.features`, not baseline dict |

---

## Migration plan

This is a breaking change to `users.role` shape and `/auth/me` response. To ship safely:

1. **PR 1 — backend: dual-write shape**
   - Add `tenant_roles` table
   - Seed defaults retroactively for all existing tenants
   - Add `users.role_id` as nullable, backfill from text column, then set NOT NULL
   - Keep `users.role` text column for now (drop in a later PR)
   - `/auth/me` returns both `role: "staff"` AND `role_obj: { ... }` (temporary)
   - Frontend continues reading `role: string`

2. **PR 2 — frontend: swap permissions module to role_obj**
   - Update `User` type, `canAccess`, call sites
   - Feature flag or staged rollout if needed
   - All existing tests should still pass — sidebar, route guards, dashboard

3. **PR 3 — backend: drop legacy column**
   - `/auth/me` returns only `role: { ... }`
   - `ALTER TABLE users DROP COLUMN role`
   - Update all backend schemas

4. **PR 4 — frontend: owner settings UI**
   - `features/roles/` folder
   - `/settings/roles` route
   - User form role dropdown switches to `useRoles()`

5. **PR 5 — cleanup**
   - Delete transitional comments, `TODO(roles)` markers
   - Update `docs/features/users.md` to reference roles feature

Why staged: the permissions system is load-bearing for security. A broken deployment means either users see features they shouldn't, or they can't access features they need. Dual-write + staged rollout lets us verify each layer before removing the previous one.

---

## Open questions

1. **Sub-permissions within a feature?** Do we need "can view members but not delete"? Starting simple with flat feature grants. If real usage demands it, upgrade to `{feature, actions: ['read', 'write', 'delete']}`.
2. **Role hierarchies?** Can a role inherit from another ("Manager = Staff + payments + reports")? Probably not v1 — flat list is easier to reason about.
3. **Audit trail?** Should role changes be logged in `activity_logs`? Yes — owners will want to see "who changed the staff role and when". Mongo activity log, standard pattern.
4. **Multi-role users?** Can one user have two roles? No — keeps the `users.role_id` FK simple. If a real use case emerges, revisit.
5. **Role templates across tenants?** Could platform offer "common role packs" (e.g., "Gym with 5+ staff" preset)? Nice-to-have, not v1.
