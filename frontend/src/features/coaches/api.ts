import { apiClient } from "@/lib/api-client"
import type {
  AssignCoachRequest,
  ClassCoach,
  Coach,
  CoachStatus,
  CreateCoachRequest,
  EarningsBreakdown,
  InviteCoachUserRequest,
  UpdateClassCoachRequest,
  UpdateCoachRequest,
} from "./types"

// ── Coach CRUD ─────────────────────────────────────────────────────────

/** List coaches in the caller's tenant. */
export function listCoaches(filters?: {
  status?: CoachStatus[]
  search?: string
  limit?: number
  offset?: number
}): Promise<Coach[]> {
  const params = new URLSearchParams()
  filters?.status?.forEach((s) => params.append("status", s))
  if (filters?.search) params.set("search", filters.search)
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset))
  const qs = params.toString()
  return apiClient.get(`/coaches${qs ? `?${qs}` : ""}`)
}

export function getCoach(id: string): Promise<Coach> {
  return apiClient.get(`/coaches/${id}`)
}

export function createCoach(data: CreateCoachRequest): Promise<Coach> {
  return apiClient.post("/coaches", data)
}

export function updateCoach(id: string, data: UpdateCoachRequest): Promise<Coach> {
  return apiClient.patch(`/coaches/${id}`, data)
}

export function freezeCoach(id: string): Promise<Coach> {
  return apiClient.post(`/coaches/${id}/freeze`)
}

export function unfreezeCoach(id: string): Promise<Coach> {
  return apiClient.post(`/coaches/${id}/unfreeze`)
}

export function cancelCoach(id: string): Promise<Coach> {
  return apiClient.post(`/coaches/${id}/cancel`)
}

export function inviteCoachUser(
  id: string,
  data: InviteCoachUserRequest,
): Promise<Coach> {
  return apiClient.post(`/coaches/${id}/invite-user`, data)
}

// ── Class-coach links ──────────────────────────────────────────────────

export function listCoachesForClass(
  classId: string,
  onlyCurrent = false,
): Promise<ClassCoach[]> {
  const qs = onlyCurrent ? "?only_current=true" : ""
  return apiClient.get(`/classes/${classId}/coaches${qs}`)
}

export function listClassesForCoach(
  coachId: string,
  onlyCurrent = false,
): Promise<ClassCoach[]> {
  const qs = onlyCurrent ? "?only_current=true" : ""
  return apiClient.get(`/coaches/${coachId}/classes${qs}`)
}

export function assignCoachToClass(
  classId: string,
  data: AssignCoachRequest,
): Promise<ClassCoach> {
  return apiClient.post(`/classes/${classId}/coaches`, data)
}

export function updateClassCoachLink(
  linkId: string,
  data: UpdateClassCoachRequest,
): Promise<ClassCoach> {
  return apiClient.patch(`/class-coaches/${linkId}`, data)
}

export function deleteClassCoachLink(linkId: string): Promise<void> {
  return apiClient.delete(`/class-coaches/${linkId}`)
}

// ── Earnings ────────────────────────────────────────────────────────────

export function getCoachEarnings(
  coachId: string,
  from: string,
  to: string,
): Promise<EarningsBreakdown> {
  const params = new URLSearchParams({ from, to })
  return apiClient.get(`/coaches/${coachId}/earnings?${params.toString()}`)
}

export function getEarningsSummary(
  from: string,
  to: string,
): Promise<EarningsBreakdown[]> {
  const params = new URLSearchParams({ from, to })
  return apiClient.get(`/coaches/earnings/summary?${params.toString()}`)
}

// ── Reassign coach on an entry ──────────────────────────────────────────

export function reassignEntryCoach(
  entryId: string,
  coachId: string | null,
): Promise<unknown> {
  return apiClient.post(`/attendance/${entryId}/reassign-coach`, {
    coach_id: coachId,
  })
}
