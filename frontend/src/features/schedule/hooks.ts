import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  bulkAction,
  cancelSession,
  createAdHocSession,
  createTemplate,
  deactivateTemplate,
  getSession,
  getTemplate,
  listSessions,
  listTemplates,
  updateSession,
  updateTemplate,
  updateTenantFeatures,
} from "./api"
import type {
  BulkActionRequest,
  CancelSessionRequest,
  CreateAdHocSessionRequest,
  CreateTemplateRequest,
  UpdateSessionRequest,
  UpdateTemplateRequest,
  UpdateTenantFeaturesRequest,
} from "./types"

// ── Queries ────────────────────────────────────────────────────────────

export function useTemplates(filters?: {
  class_id?: string
  only_active?: boolean
}) {
  return useQuery({
    queryKey: ["schedule-templates", filters ?? {}],
    queryFn: () => listTemplates(filters),
  })
}

export function useTemplate(id: string) {
  return useQuery({
    queryKey: ["schedule-templates", id],
    queryFn: () => getTemplate(id),
    enabled: !!id,
  })
}

export function useSessions(params: {
  from: string
  to: string
  class_id?: string
  coach_id?: string
  include_cancelled?: boolean
}) {
  return useQuery({
    queryKey: ["schedule-sessions", params],
    queryFn: () => listSessions(params),
  })
}

export function useSession(id: string) {
  return useQuery({
    queryKey: ["schedule-sessions", id],
    queryFn: () => getSession(id),
    enabled: !!id,
  })
}

// ── Mutations ──────────────────────────────────────────────────────────

export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTemplateRequest) => createTemplate(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule-templates"] })
      qc.invalidateQueries({ queryKey: ["schedule-sessions"] })
    },
  })
}

export function useUpdateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTemplateRequest }) =>
      updateTemplate(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule-templates"] })
      qc.invalidateQueries({ queryKey: ["schedule-sessions"] })
    },
  })
}

export function useDeactivateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deactivateTemplate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule-templates"] })
      qc.invalidateQueries({ queryKey: ["schedule-sessions"] })
    },
  })
}

export function useCreateAdHocSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAdHocSessionRequest) => createAdHocSession(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedule-sessions"] }),
  })
}

export function useUpdateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateSessionRequest }) =>
      updateSession(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedule-sessions"] }),
  })
}

export function useCancelSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CancelSessionRequest }) =>
      cancelSession(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedule-sessions"] }),
  })
}

export function useBulkAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BulkActionRequest) => bulkAction(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedule-sessions"] }),
  })
}

export function useUpdateTenantFeatures() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      tenantId,
      data,
    }: {
      tenantId: string
      data: UpdateTenantFeaturesRequest
    }) => updateTenantFeatures(tenantId, data),
    onSuccess: (tenant) => {
      qc.invalidateQueries({ queryKey: ["tenants"] })
      qc.setQueryData(["tenants", tenant.id], tenant)
    },
  })
}
