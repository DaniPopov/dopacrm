import { apiClient } from "@/lib/api-client"
import type {
  AddActivityRequest,
  AssignLeadRequest,
  ConvertLeadRequest,
  ConvertLeadResponse,
  CreateLeadRequest,
  Lead,
  LeadActivity,
  LeadSource,
  LeadStats,
  LeadStatus,
  LostReasonRow,
  SetLeadStatusRequest,
  UpdateLeadRequest,
} from "./types"

// ── Lead CRUD ───────────────────────────────────────────────────────

export function listLeads(filters?: {
  status?: LeadStatus[]
  source?: LeadSource[]
  assignedTo?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<Lead[]> {
  const params = new URLSearchParams()
  filters?.status?.forEach((s) => params.append("status", s))
  filters?.source?.forEach((s) => params.append("source", s))
  if (filters?.assignedTo) params.set("assigned_to", filters.assignedTo)
  if (filters?.search) params.set("search", filters.search)
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset))
  const qs = params.toString()
  return apiClient.get(`/leads${qs ? `?${qs}` : ""}`)
}

export function getLead(id: string): Promise<Lead> {
  return apiClient.get(`/leads/${id}`)
}

export function createLead(data: CreateLeadRequest): Promise<Lead> {
  return apiClient.post("/leads", data)
}

export function updateLead(id: string, data: UpdateLeadRequest): Promise<Lead> {
  return apiClient.patch(`/leads/${id}`, data)
}

export function setLeadStatus(
  id: string,
  data: SetLeadStatusRequest,
): Promise<Lead> {
  return apiClient.post(`/leads/${id}/status`, data)
}

export function assignLead(id: string, data: AssignLeadRequest): Promise<Lead> {
  return apiClient.post(`/leads/${id}/assign`, data)
}

export function convertLead(
  id: string,
  data: ConvertLeadRequest,
): Promise<ConvertLeadResponse> {
  return apiClient.post(`/leads/${id}/convert`, data)
}

// ── Activities ──────────────────────────────────────────────────────

export function listActivities(
  leadId: string,
  filters?: { limit?: number; offset?: number },
): Promise<LeadActivity[]> {
  const params = new URLSearchParams()
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset))
  const qs = params.toString()
  return apiClient.get(`/leads/${leadId}/activities${qs ? `?${qs}` : ""}`)
}

export function addActivity(
  leadId: string,
  data: AddActivityRequest,
): Promise<LeadActivity> {
  return apiClient.post(`/leads/${leadId}/activities`, data)
}

// ── Stats + lost reasons ────────────────────────────────────────────

export function getLeadStats(): Promise<LeadStats> {
  return apiClient.get("/leads/stats")
}

export function listLostReasons(filters?: {
  days?: number
  limit?: number
}): Promise<LostReasonRow[]> {
  const params = new URLSearchParams()
  if (filters?.days !== undefined) params.set("days", String(filters.days))
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  const qs = params.toString()
  return apiClient.get(`/leads/lost-reasons${qs ? `?${qs}` : ""}`)
}
