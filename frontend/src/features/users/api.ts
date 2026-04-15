import { apiClient } from "@/lib/api-client"
import type { CreateUserRequest, UpdateUserRequest, User } from "./types"

/**
 * Create a new user.
 *
 * `POST /api/v1/users` — super_admin only. For platform-level users
 * (super_admin), omit `tenant_id`. For tenant-scoped users
 * (owner/staff/sales), pass the target `tenant_id`.
 *
 * @throws `ApiError(403)` — caller is not super_admin
 * @throws `ApiError(409)` — email already in use in the target scope
 * @throws `ApiError(422)` — validation error (missing password, bad role, …)
 */
export function createUser(data: CreateUserRequest): Promise<User> {
  return apiClient.post("/users", data)
}

/**
 * List users in a specific tenant.
 *
 * `GET /api/v1/tenants/{id}/users` — super_admin only. Used by the
 * tenant detail page's Users section to list staff for that gym.
 *
 * @throws `ApiError(403)` — caller is not super_admin
 * @throws `ApiError(404)` — tenant not found
 */
export function listUsersForTenant(tenantId: string): Promise<User[]> {
  return apiClient.get(`/tenants/${tenantId}/users`)
}

/**
 * Update a user's profile (partial). owner+ only on the backend.
 *
 * @throws `ApiError(403)` — caller lacks permission
 * @throws `ApiError(404)` — user not found
 */
export function updateUser(id: string, data: UpdateUserRequest): Promise<User> {
  return apiClient.patch(`/users/${id}`, data)
}

/**
 * Soft-delete a user (sets `is_active=false`). owner+ only.
 *
 * @throws `ApiError(403)` — caller lacks permission
 * @throws `ApiError(404)` — user not found
 */
export function deleteUser(id: string): Promise<void> {
  return apiClient.delete(`/users/${id}`)
}
