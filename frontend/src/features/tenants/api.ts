import { apiClient } from "@/lib/api-client"
import type {
  CreateTenantRequest,
  Tenant,
  UpdateTenantRequest,
  UploadResponse,
} from "./types"

export function listTenants(): Promise<Tenant[]> {
  return apiClient.get("/tenants")
}

export function getTenant(id: string): Promise<Tenant> {
  return apiClient.get(`/tenants/${id}`)
}

export function createTenant(data: CreateTenantRequest): Promise<Tenant> {
  return apiClient.post("/tenants", data)
}

export function updateTenant(id: string, data: UpdateTenantRequest): Promise<Tenant> {
  return apiClient.patch(`/tenants/${id}`, data)
}

export function suspendTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/suspend`)
}

/** Reactivate a suspended/trial/cancelled tenant. */
export function activateTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/activate`)
}

/** Soft-delete a tenant (status=cancelled). Reversible via activate. */
export function cancelTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/cancel`)
}

/**
 * Upload a logo file. Returns the S3 key (save as ``logo_url``) and a
 * short-lived presigned URL for immediate preview.
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
