/**
 * Auth types.
 *
 * Type definitions are generated from the backend's OpenAPI spec —
 * we re-export them from `lib/api-types.ts` so feature code keeps the
 * familiar import path. Runtime constants (like ALL_GYM_ROLES) and JSDoc
 * stay here.
 *
 * Roles mirror the backend's hierarchy:
 * - super_admin: platform-level, tenant_id=null, manages all gyms
 * - owner:       full tenant access, billing, config, employee permissions
 * - staff:       day-to-day ops (check-in, payments, members)
 * - sales:       lead pipeline, trials, conversions
 * - coach:       trainer — read-only baseline, linked 1:1 to a coaches row
 *
 * What staff/sales can *see* beyond the baseline is controlled by
 * per-tenant feature visibility (owner-configured). See permissions.ts.
 *
 * Localized labels live on ``GYM_ROLE_LABELS`` so dropdowns stay in sync
 * with this list — don't hand-roll <option> lists with hardcoded roles.
 */

export type {
  LoginRequest,
  TokenResponse,
  Role,
  User,
} from "@/lib/api-types"

import type { Role } from "@/lib/api-types"

export const ALL_GYM_ROLES: Role[] = ["owner", "staff", "sales", "coach"]

export const GYM_ROLE_LABELS: Record<Role, string> = {
  super_admin: "פלטפורמה",
  owner: "בעלים",
  staff: "צוות",
  sales: "מכירות",
  coach: "מאמן",
}
