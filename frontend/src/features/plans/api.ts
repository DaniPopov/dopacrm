import { apiClient } from "@/lib/api-client"
import type {
  CreatePlanRequest,
  MembershipPlan,
  UpdatePlanRequest,
} from "./types"

/**
 * List membership plans in the caller's tenant.
 *
 * `GET /api/v1/plans` — tenant-scoped. Any tenant user (owner/staff/sales)
 * can read. super_admin is rejected (platform-level, not gym).
 *
 * @param includeInactive - Include deactivated plans in the response. Defaults to false.
 * @param limit - Page size. Default 100, max 200.
 * @param offset - Skip N results for pagination.
 * @throws `ApiError(403)` — caller is super_admin or has no tenant
 */
export function listPlans(options?: {
  includeInactive?: boolean
  limit?: number
  offset?: number
}): Promise<MembershipPlan[]> {
  const params = new URLSearchParams()
  if (options?.includeInactive) params.set("include_inactive", "true")
  if (options?.limit !== undefined) params.set("limit", String(options.limit))
  if (options?.offset !== undefined) params.set("offset", String(options.offset))
  const qs = params.toString()
  return apiClient.get(`/plans${qs ? `?${qs}` : ""}`)
}

/**
 * Fetch one plan by ID. Returns 404 for plans in other tenants
 * (we don't leak existence across tenants).
 *
 * @throws `ApiError(404)` — plan not found OR in another tenant
 */
export function getPlan(id: string): Promise<MembershipPlan> {
  return apiClient.get(`/plans/${id}`)
}

/**
 * Create a new plan (+ entitlements) in the caller's tenant. Owner-only.
 *
 * Pass `entitlements: []` (or omit) for "unlimited any class".
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(409)` — plan with same name already exists in tenant
 * @throws `ApiError(422)` — invalid shape (e.g. one_time plan without duration_days,
 *                          entitlement with reset='unlimited' but quantity provided)
 */
export function createPlan(data: CreatePlanRequest): Promise<MembershipPlan> {
  return apiClient.post("/plans", data)
}

/**
 * Partial update of a plan. Owner-only.
 *
 * Entitlement semantics: omit `entitlements` to leave them untouched,
 * pass `[]` to clear all rules, pass a list to REPLACE the full set.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — plan not found
 * @throws `ApiError(409)` — rename collides with another plan in tenant
 * @throws `ApiError(422)` — invalid shape
 */
export function updatePlan(
  id: string,
  data: UpdatePlanRequest,
): Promise<MembershipPlan> {
  return apiClient.patch(`/plans/${id}`, data)
}

/**
 * Soft-deactivate a plan (is_active → false). Existing subscriptions keep
 * working; new ones can't reference this plan. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — plan not found
 */
export function deactivatePlan(id: string): Promise<MembershipPlan> {
  return apiClient.post(`/plans/${id}/deactivate`)
}

/**
 * Re-activate a deactivated plan. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — plan not found
 */
export function activatePlan(id: string): Promise<MembershipPlan> {
  return apiClient.post(`/plans/${id}/activate`)
}
