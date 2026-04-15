import { apiClient } from "@/lib/api-client"
import type {
  CreateMemberRequest,
  Member,
  MemberStatus,
  UpdateMemberRequest,
} from "./types"

/**
 * List members in the caller's tenant.
 *
 * `GET /api/v1/members` — tenant-scoped. super_admin is rejected
 * (they're platform-level, not gym-level).
 *
 * @param filters - Optional status (repeat for multiple), search, pagination
 * @throws `ApiError(403)` — caller is super_admin (member ops are gym-scoped)
 */
export function listMembers(filters?: {
  status?: MemberStatus[]
  search?: string
  limit?: number
  offset?: number
}): Promise<Member[]> {
  const params = new URLSearchParams()
  filters?.status?.forEach((s) => params.append("status", s))
  if (filters?.search) params.set("search", filters.search)
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset))
  const qs = params.toString()
  return apiClient.get(`/members${qs ? `?${qs}` : ""}`)
}

/**
 * Fetch a single member by ID. Returns 404 even for members in other
 * tenants (we don't leak existence).
 *
 * @throws `ApiError(404)` — member not found OR in another tenant
 */
export function getMember(id: string): Promise<Member> {
  return apiClient.get(`/members/${id}`)
}

/**
 * Create a member in the caller's tenant.
 *
 * Server defaults: status=active, join_date=today.
 *
 * @throws `ApiError(409)` — phone already in use within this tenant
 * @throws `ApiError(422)` — validation error
 */
export function createMember(data: CreateMemberRequest): Promise<Member> {
  return apiClient.post("/members", data)
}

/**
 * Partial update. Status transitions go through the dedicated endpoints
 * (freeze/unfreeze/cancel) — not this one.
 *
 * @throws `ApiError(404)` — member not found
 */
export function updateMember(id: string, data: UpdateMemberRequest): Promise<Member> {
  return apiClient.patch(`/members/${id}`, data)
}

/**
 * Freeze an active member (pauses their subscription).
 *
 * @param until - Optional auto-unfreeze date (YYYY-MM-DD). Null = indefinite.
 * @throws `ApiError(409)` — member is not currently active
 */
export function freezeMember(id: string, until?: string): Promise<Member> {
  return apiClient.post(`/members/${id}/freeze`, { until: until ?? null })
}

/**
 * Unfreeze a frozen member (returns them to active).
 *
 * @throws `ApiError(409)` — member is not currently frozen
 */
export function unfreezeMember(id: string): Promise<Member> {
  return apiClient.post(`/members/${id}/unfreeze`)
}

/**
 * Cancel a member (terminal). owner+ only — staff is rejected.
 *
 * @throws `ApiError(403)` — caller is not owner (or super_admin)
 * @throws `ApiError(409)` — member is already cancelled
 */
export function cancelMember(id: string): Promise<Member> {
  return apiClient.post(`/members/${id}/cancel`)
}
