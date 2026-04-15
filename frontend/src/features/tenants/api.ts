import { apiClient } from "@/lib/api-client"
import type { components } from "@/lib/api-schema"
import type {
  CreateTenantRequest,
  Tenant,
  UpdateTenantRequest,
  UploadResponse,
} from "./types"

export type TenantStats = components["schemas"]["TenantStatsResponse"]

/**
 * List all tenants on the platform.
 *
 * `GET /api/v1/tenants` — super_admin only.
 *
 * @returns Array of `Tenant` objects
 * @throws `ApiError(403)` — caller is not super_admin
 */
export function listTenants(): Promise<Tenant[]> {
  return apiClient.get("/tenants")
}

/**
 * Fetch a single tenant by ID. Includes `logo_presigned_url` for display.
 *
 * `GET /api/v1/tenants/{id}`
 *
 * @param id - Tenant UUID
 * @throws `ApiError(404)` — tenant not found
 */
export function getTenant(id: string): Promise<Tenant> {
  return apiClient.get(`/tenants/${id}`)
}

/**
 * Onboard a new gym as a tenant.
 *
 * `POST /api/v1/tenants` — super_admin only. The backend auto-assigns the
 * default SaaS plan, sets `status=trial`, and `trial_ends_at=now+14d`.
 *
 * @param data - Tenant details (`slug` and `name` required, rest optional)
 * @returns The newly created `Tenant`
 * @throws `ApiError(409)` — slug already taken
 * @throws `ApiError(422)` — validation error (missing fields, bad format)
 */
export function createTenant(data: CreateTenantRequest): Promise<Tenant> {
  return apiClient.post("/tenants", data)
}

/**
 * Partial update of a tenant's fields.
 *
 * `PATCH /api/v1/tenants/{id}` — super_admin only.
 *
 * @param id - Tenant UUID
 * @param data - Fields to update (only provided fields change)
 * @throws `ApiError(404)` — tenant not found
 * @throws `ApiError(409)` — slug conflict with another tenant
 */
export function updateTenant(id: string, data: UpdateTenantRequest): Promise<Tenant> {
  return apiClient.patch(`/tenants/${id}`, data)
}

/**
 * Suspend a tenant. Users of this gym can no longer log in.
 *
 * `POST /api/v1/tenants/{id}/suspend` — super_admin only.
 *
 * @param id - Tenant UUID
 * @throws `ApiError(404)` — tenant not found
 */
export function suspendTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/suspend`)
}

/**
 * Reactivate a suspended, trial, or cancelled tenant.
 *
 * `POST /api/v1/tenants/{id}/activate` — super_admin only.
 *
 * @param id - Tenant UUID
 * @throws `ApiError(404)` — tenant not found
 */
export function activateTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/activate`)
}

/**
 * Soft-delete a tenant (sets `status=cancelled`). Reversible via `activateTenant()`.
 *
 * `POST /api/v1/tenants/{id}/cancel` — super_admin only.
 *
 * @param id - Tenant UUID
 * @throws `ApiError(404)` — tenant not found
 */
export function cancelTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/cancel`)
}

/**
 * Fetch per-tenant counters for the detail page.
 *
 * `GET /api/v1/tenants/{id}/stats` — super_admin can view any tenant;
 * tenant users can only view their own gym.
 *
 * @throws `ApiError(403)` — caller is not allowed to view this tenant
 * @throws `ApiError(404)` — tenant not found
 */
export function getTenantStats(id: string): Promise<TenantStats> {
  return apiClient.get(`/tenants/${id}/stats`)
}

/**
 * Upload a logo image to S3.
 *
 * `POST /api/v1/uploads/logo` — multipart form data. Does NOT go through
 * `apiClient` because the body is `FormData`, not JSON.
 *
 * Returns the S3 key (save as `logo_url` on the tenant) and a short-lived
 * presigned URL for immediate preview in the UI.
 *
 * @param file - The image `File` to upload (PNG, JPG, WebP, or SVG, max 2MB)
 * @returns `{ key, presigned_url }`
 * @throws `Error(413)` — file too large (>2MB)
 * @throws `Error(415)` — unsupported file type
 */
export async function uploadLogo(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)

  const res = await fetch("/api/v1/uploads/logo", {
    method: "POST",
    credentials: "include",
    body: formData,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Upload failed: ${res.status}`,
    )
  }
  return res.json()
}
