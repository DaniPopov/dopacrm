import type { Role, User } from "./types"

/**
 * Feature visibility — central permissions module.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * TODO(roles): This is the PLACEHOLDER implementation.
 * ═══════════════════════════════════════════════════════════════════════
 *
 * The real model is dynamic, per-tenant, owner-configurable roles — see
 * `docs/features/roles.md` for the full spec and migration plan.
 *
 * When that lands, this file collapses to:
 *
 *     export function canAccess(user, feature) {
 *       return user?.role.features.includes(feature) ?? false
 *     }
 *
 * And `BASELINE`, `TenantOverrides`, `accessibleFeatures` go away — the
 * backend returns the role as `{ id, name, features, is_system }` on
 * /auth/me, and the frontend just reads `user.role.features` directly.
 *
 * **Crucially: call sites (Sidebar, RequireFeature, any future component)
 * do not change.** They already call `canAccess(user, feature)`. The whole
 * point of this indirection is to make that swap a one-file PR.
 *
 * DO NOT add new hardcoded role→feature rules to the BASELINE dict below
 * without updating `docs/features/roles.md` — every new entry is debt that
 * has to be migrated to the tenant_roles table later.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * Current (temporary) design
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Two layers:
 *
 *   1. BASELINE (hardcoded, role → features[])
 *      What a role *can* see at the system level. super_admin sees platform
 *      features; owner sees everything tenant-scoped; staff and sales get
 *      the minimum safe default (dashboard only).
 *
 *   2. TENANT OVERRIDES (per-tenant, owner-configured) — NOT WIRED YET
 *      Placeholder shape. In the real system this is replaced by the full
 *      tenant_roles row, not a side-table.
 *
 * Owner and super_admin are never overridden — they always see their full
 * baseline. Only staff/sales are configurable.
 */

/**
 * Every permission-gated feature in the app.
 * Add new features here as you build them.
 */
export type Feature =
  | "dashboard" // everyone
  // Platform admin — user management lives inside the tenant detail page,
  // so there's no "platform_users" feature (dropped 2026-04-15).
  | "tenants"
  // Gym-scoped
  | "members"
  | "classes" // class-type catalog (gym-scoped)
  | "plans"
  | "attendance" // check-in / front desk
  | "coaches" // trainers + payroll estimate (GATED — per-tenant flag)
  | "schedule" // weekly calendar + sessions (GATED — per-tenant flag)
  | "leads"
  | "payments"
  | "reports"
  | "settings" // tenant settings — owner only

/**
 * Features that require a tenant flag in addition to the role baseline.
 * Mirror of ``GatedFeature`` on the backend (``app/core/feature_flags.py``).
 *
 * If a feature is in this set, ``canAccess`` returns false unless
 * ``tenantFeatures[feature]`` is truthy. Ungated features (members,
 * attendance, etc.) ignore the tenantFeatures map.
 */
export const GATED_FEATURES: Set<Feature> = new Set(["coaches", "schedule", "leads"])

/**
 * Baseline: what each role sees without any owner overrides.
 *
 * - super_admin: platform features only (doesn't touch gym data)
 * - owner:       everything tenant-scoped
 * - staff:       dashboard only — owner grants the rest
 * - sales:       dashboard only — owner grants the rest
 */
const BASELINE: Record<Role, Feature[]> = {
  super_admin: ["dashboard", "tenants"],
  owner: [
    "dashboard",
    "members",
    "classes",
    "plans",
    "attendance",
    "coaches",
    "schedule",
    "leads",
    "payments",
    "reports",
    "settings",
  ],
  // Staff handles day-to-day ops — attendance is the highest-frequency
  // front-desk task. Members + classes context for the check-in flow.
  // Leads gives staff read-only visibility (so they can spot a walk-in's
  // lead history at check-in); the backend enforces read-only via
  // ``_require_writer`` on any mutation.
  staff: ["dashboard", "members", "classes", "attendance", "leads"],
  // Sales converts leads → members. Reads classes when enrolling; no
  // attendance (check-in is a staff/operations task). Full leads access.
  sales: ["dashboard", "members", "classes", "leads"],
  // Coach (logged-in trainer) — read-only baseline. Sees only their
  // own classes + attendance rosters + earnings. All scoping is
  // enforced server-side; the frontend feature gates just control
  // sidebar visibility. Schedule baseline is read-only too — coach
  // sees their own sessions, can't edit.
  coach: ["dashboard", "classes", "attendance", "coaches", "schedule"],
}

/**
 * Features that an owner is allowed to *grant* to staff/sales.
 *
 * Notably excludes `settings` (owner-only) and `platform_users`/`tenants`
 * (super_admin-only). Used to build the owner's permission grid UI.
 */
export const GRANTABLE_FEATURES: Feature[] = [
  "members",
  "classes",
  "plans",
  "attendance",
  "coaches",
  "schedule",
  "leads",
  "payments",
  "reports",
]

/**
 * Per-tenant overrides — what the owner has granted to each employee role.
 *
 * TODO: Load from backend. Currently always empty, so behavior matches
 * the pre-permissions-module state. When the tenant_config endpoint
 * lands, plumb the response through auth-provider and pass it in here.
 */
export interface TenantOverrides {
  staff: Feature[]
  sales: Feature[]
}

const EMPTY_OVERRIDES: TenantOverrides = { staff: [], sales: [] }

/**
 * Per-tenant feature flags from ``tenants.features_enabled``.
 * Map of gated feature name → enabled (true/false). Missing key = OFF.
 *
 * Wired through ``auth-provider`` from the user's tenant. Default empty
 * so super_admin / not-yet-loaded states fall through cleanly (super_admin
 * doesn't consult gated features for tenant-scoped checks anyway).
 */
export type TenantFeatures = Record<string, boolean>

const EMPTY_TENANT_FEATURES: TenantFeatures = {}

function isGated(feature: Feature): boolean {
  return GATED_FEATURES.has(feature)
}

/**
 * Does this user have access to this feature?
 *
 * Three layers of check:
 * 1. Role baseline + overrides (staff/sales).
 * 2. Tenant feature flag — for gated features (coaches, schedule), the
 *    flag must be on regardless of role.
 *
 * `overrides` and `tenantFeatures` are optional; default empty so
 * tests + non-feature-aware code paths still work.
 */
export function canAccess(
  user: User | null | undefined,
  feature: Feature,
  overrides: TenantOverrides = EMPTY_OVERRIDES,
  tenantFeatures: TenantFeatures = EMPTY_TENANT_FEATURES,
): boolean {
  if (!user) return false

  // Gated feature: tenant flag must be on. super_admin is the
  // platform role and rarely consults gated features in their
  // baseline, but if they did (e.g. via /tenants/{id} sub-pages), we
  // still respect the gate.
  if (isGated(feature) && !tenantFeatures[feature]) return false

  const baseline = BASELINE[user.role]
  if (baseline.includes(feature)) return true

  if (user.role === "staff") return overrides.staff.includes(feature)
  if (user.role === "sales") return overrides.sales.includes(feature)
  return false
}

/**
 * All features a user can see. Handy for building nav menus.
 */
export function accessibleFeatures(
  user: User | null | undefined,
  overrides: TenantOverrides = EMPTY_OVERRIDES,
  tenantFeatures: TenantFeatures = EMPTY_TENANT_FEATURES,
): Feature[] {
  if (!user) return []
  const baseline = BASELINE[user.role]
  let raw: Feature[] = baseline
  if (user.role === "staff") raw = [...baseline, ...overrides.staff]
  else if (user.role === "sales") raw = [...baseline, ...overrides.sales]
  // Filter out gated features the tenant hasn't enabled — same rule
  // as canAccess but in bulk.
  return raw.filter((f) => !isGated(f) || tenantFeatures[f])
}
