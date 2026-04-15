import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createUser, deleteUser, listUsersForTenant, updateUser } from "./api"
import type { CreateUserRequest, UpdateUserRequest } from "./types"

/** Fetch users for one tenant. Query key: `["tenants", tenantId, "users"]`. */
export function useTenantUsers(tenantId: string) {
  return useQuery({
    queryKey: ["tenants", tenantId, "users"],
    queryFn: () => listUsersForTenant(tenantId),
    enabled: !!tenantId,
  })
}

/**
 * Create a user. Invalidates both the per-tenant list and the tenant
 * stats (total_users count) so the UI refreshes automatically.
 */
export function useCreateUser(tenantId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateUserRequest) => createUser(data),
    onSuccess: () => {
      if (tenantId) {
        qc.invalidateQueries({ queryKey: ["tenants", tenantId, "users"] })
        qc.invalidateQueries({ queryKey: ["tenants", tenantId, "stats"] })
      }
    },
  })
}

export function useUpdateUser(tenantId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateUserRequest }) =>
      updateUser(id, data),
    onSuccess: () => {
      if (tenantId) {
        qc.invalidateQueries({ queryKey: ["tenants", tenantId, "users"] })
      }
    },
  })
}

export function useDeleteUser(tenantId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => {
      if (tenantId) {
        qc.invalidateQueries({ queryKey: ["tenants", tenantId, "users"] })
        qc.invalidateQueries({ queryKey: ["tenants", tenantId, "stats"] })
      }
    },
  })
}
