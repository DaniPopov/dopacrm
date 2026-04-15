import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  activateTenant,
  cancelTenant,
  createTenant,
  getTenant,
  getTenantStats,
  listTenants,
  suspendTenant,
  updateTenant,
  uploadLogo,
} from "./api"
import type { CreateTenantRequest, UpdateTenantRequest } from "./types"

/** Fetch all tenants. Query key: `["tenants"]`. Auto-refetches on tab focus. */
export function useTenants() {
  return useQuery({
    queryKey: ["tenants"],
    queryFn: listTenants,
  })
}

/** Fetch a single tenant by ID. Query key: `["tenants", id]`. Disabled when `id` is empty. */
export function useTenant(id: string) {
  return useQuery({
    queryKey: ["tenants", id],
    queryFn: () => getTenant(id),
    enabled: !!id,
  })
}

/** Fetch per-tenant stats (member + user counts). Invalidated by user/member mutations. */
export function useTenantStats(id: string) {
  return useQuery({
    queryKey: ["tenants", id, "stats"],
    queryFn: () => getTenantStats(id),
    enabled: !!id,
  })
}

/** Create a new tenant. Invalidates the tenant list on success so the table auto-refreshes. */
export function useCreateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTenantRequest) => createTenant(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

/** Update a tenant's fields. Invalidates the tenant list on success. */
export function useUpdateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTenantRequest }) =>
      updateTenant(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

/** Suspend a tenant. Invalidates the tenant list on success. */
export function useSuspendTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => suspendTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

/** Reactivate a suspended/trial/cancelled tenant. Invalidates the tenant list on success. */
export function useActivateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => activateTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

/** Soft-delete a tenant (status=cancelled). Invalidates the tenant list on success. */
export function useCancelTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

/** Upload a logo image to S3. Returns `{ key, presigned_url }`. */
export function useUploadLogo() {
  return useMutation({
    mutationFn: (file: File) => uploadLogo(file),
  })
}
