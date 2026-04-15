import { apiClient } from "@/lib/api-client"
import type { components } from "@/lib/api-schema"

export type PlatformStats = components["schemas"]["PlatformStatsResponse"]

/**
 * Fetch platform-wide aggregate stats for the super_admin dashboard.
 *
 * `GET /api/v1/admin/stats` — super_admin only.
 *
 * Returns counts for total/active tenants, new tenants this month,
 * total users (including super_admin), and total members across all
 * tenants.
 *
 * @throws `ApiError(401)` — not authenticated
 * @throws `ApiError(403)` — caller is not super_admin
 */
export function getPlatformStats(): Promise<PlatformStats> {
  return apiClient.get("/admin/stats")
}
