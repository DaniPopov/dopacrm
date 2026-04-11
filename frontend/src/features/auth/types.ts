export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

/**
 * System roles. Mirrors the backend's role hierarchy.
 *
 * - super_admin: platform-level, tenant_id=null, manages all gyms
 * - owner:       full tenant access, billing, config, employee permissions
 * - staff:       day-to-day ops (check-in, payments, members)
 * - sales:       lead pipeline, trials, conversions
 *
 * What staff/sales can *see* beyond the baseline is controlled by
 * per-tenant feature visibility (owner-configured). See permissions.ts.
 */
export type Role = "super_admin" | "owner" | "staff" | "sales"

export const ALL_GYM_ROLES: Role[] = ["owner", "staff", "sales"]

export interface User {
  id: string
  email: string
  role: Role
  tenant_id: string | null
  is_active: boolean
  oauth_provider: string | null
  created_at: string
  updated_at: string
}
