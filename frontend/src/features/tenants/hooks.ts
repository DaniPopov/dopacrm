import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  activateTenant,
  cancelTenant,
  createTenant,
  getTenant,
  listTenants,
  suspendTenant,
  updateTenant,
  uploadLogo,
} from "./api"
import type { CreateTenantRequest, UpdateTenantRequest } from "./types"

export function useTenants() {
  return useQuery({
    queryKey: ["tenants"],
    queryFn: listTenants,
  })
}

export function useTenant(id: string) {
  return useQuery({
    queryKey: ["tenants", id],
    queryFn: () => getTenant(id),
    enabled: !!id,
  })
}

export function useCreateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTenantRequest) => createTenant(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useUpdateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTenantRequest }) =>
      updateTenant(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useSuspendTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => suspendTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useActivateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => activateTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useCancelTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useUploadLogo() {
  return useMutation({
    mutationFn: (file: File) => uploadLogo(file),
  })
}
