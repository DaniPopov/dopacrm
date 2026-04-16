import { apiClient } from "@/lib/api-client"
import type {
  CreateGymClassRequest,
  GymClass,
  UpdateGymClassRequest,
} from "./types"

/**
 * List classes in the caller's tenant.
 *
 * `GET /api/v1/classes` — tenant-scoped. Any tenant user (owner/staff/sales)
 * can read. super_admin is rejected (they're platform-level, not gym).
 *
 * @param includeInactive - If true, deactivated classes are included in the
 *                          response. Defaults to false (active-only).
 * @param limit - Page size. Default 100, max 200.
 * @param offset - Skip N results for pagination.
 * @throws `ApiError(403)` — caller is super_admin or has no tenant
 */
export function listClasses(options?: {
  includeInactive?: boolean
  limit?: number
  offset?: number
}): Promise<GymClass[]> {
  const params = new URLSearchParams()
  if (options?.includeInactive) params.set("include_inactive", "true")
  if (options?.limit !== undefined) params.set("limit", String(options.limit))
  if (options?.offset !== undefined) params.set("offset", String(options.offset))
  const qs = params.toString()
  return apiClient.get(`/classes${qs ? `?${qs}` : ""}`)
}

/**
 * Fetch one class by ID. Returns 404 for classes in other tenants
 * (we don't leak existence across tenants).
 *
 * @throws `ApiError(404)` — class not found OR in another tenant
 */
export function getClass(id: string): Promise<GymClass> {
  return apiClient.get(`/classes/${id}`)
}

/**
 * Create a new class in the caller's tenant. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(409)` — class with same name already exists in tenant
 * @throws `ApiError(422)` — validation error (missing name, too long, ...)
 */
export function createClass(data: CreateGymClassRequest): Promise<GymClass> {
  return apiClient.post("/classes", data)
}

/**
 * Partial update of a class. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — class not found
 * @throws `ApiError(409)` — renaming to a name another class already uses
 */
export function updateClass(
  id: string,
  data: UpdateGymClassRequest,
): Promise<GymClass> {
  return apiClient.patch(`/classes/${id}`, data)
}

/**
 * Soft-deactivate a class (is_active → false). Existing plan_entitlements
 * and passes keep working; new subscriptions can't reference it. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — class not found
 */
export function deactivateClass(id: string): Promise<GymClass> {
  return apiClient.post(`/classes/${id}/deactivate`)
}

/**
 * Re-activate a deactivated class. Owner-only.
 *
 * @throws `ApiError(403)` — caller is not owner
 * @throws `ApiError(404)` — class not found
 */
export function activateClass(id: string): Promise<GymClass> {
  return apiClient.post(`/classes/${id}/activate`)
}
