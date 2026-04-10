import { apiClient } from "@/lib/api-client"
import type { Tenant, CreateTenantRequest, UpdateTenantRequest } from "./types"

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
