import { apiClient } from "@/lib/api-client"
import type {
  BulkActionRequest,
  BulkActionResponse,
  CancelSessionRequest,
  ClassSession,
  CreateAdHocSessionRequest,
  CreateTemplateRequest,
  ScheduleTemplate,
  UpdateSessionRequest,
  UpdateTemplateRequest,
  UpdateTenantFeaturesRequest,
} from "./types"
import type { Tenant } from "@/lib/api-types"

// ── Templates ─────────────────────────────────────────────────────────

export function listTemplates(params?: {
  class_id?: string
  only_active?: boolean
}): Promise<ScheduleTemplate[]> {
  const qs = new URLSearchParams()
  if (params?.class_id) qs.set("class_id", params.class_id)
  if (params?.only_active) qs.set("only_active", "true")
  const q = qs.toString()
  return apiClient.get(`/schedule/templates${q ? `?${q}` : ""}`)
}

export function getTemplate(id: string): Promise<ScheduleTemplate> {
  return apiClient.get(`/schedule/templates/${id}`)
}

export function createTemplate(
  data: CreateTemplateRequest,
): Promise<ScheduleTemplate> {
  return apiClient.post("/schedule/templates", data)
}

export function updateTemplate(
  id: string,
  data: UpdateTemplateRequest,
): Promise<ScheduleTemplate> {
  return apiClient.patch(`/schedule/templates/${id}`, data)
}

export function deactivateTemplate(id: string): Promise<ScheduleTemplate> {
  return apiClient.delete(`/schedule/templates/${id}`)
}

// ── Sessions ──────────────────────────────────────────────────────────

export function listSessions(params: {
  from: string // ISO datetime
  to: string
  class_id?: string
  coach_id?: string
  include_cancelled?: boolean
}): Promise<ClassSession[]> {
  const qs = new URLSearchParams({ from: params.from, to: params.to })
  if (params.class_id) qs.set("class_id", params.class_id)
  if (params.coach_id) qs.set("coach_id", params.coach_id)
  if (params.include_cancelled === false)
    qs.set("include_cancelled", "false")
  return apiClient.get(`/schedule/sessions?${qs.toString()}`)
}

export function getSession(id: string): Promise<ClassSession> {
  return apiClient.get(`/schedule/sessions/${id}`)
}

export function createAdHocSession(
  data: CreateAdHocSessionRequest,
): Promise<ClassSession> {
  return apiClient.post("/schedule/sessions", data)
}

export function updateSession(
  id: string,
  data: UpdateSessionRequest,
): Promise<ClassSession> {
  return apiClient.patch(`/schedule/sessions/${id}`, data)
}

export function cancelSession(
  id: string,
  data: CancelSessionRequest,
): Promise<ClassSession> {
  return apiClient.post(`/schedule/sessions/${id}/cancel`, data)
}

// ── Bulk action ──────────────────────────────────────────────────────

export function bulkAction(data: BulkActionRequest): Promise<BulkActionResponse> {
  return apiClient.post("/schedule/bulk-action", data)
}

// ── Tenant features ──────────────────────────────────────────────────

export function updateTenantFeatures(
  tenantId: string,
  data: UpdateTenantFeaturesRequest,
): Promise<Tenant> {
  return apiClient.patch(`/tenants/${tenantId}/features`, data)
}
