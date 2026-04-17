import { apiClient } from "@/lib/api-client"
import type {
  AttendanceSummaryItem,
  ClassEntry,
  QuotaCheckResult,
  RecordEntryRequest,
  UndoEntryRequest,
} from "./types"

/** Peek: does this (member, class) combo pass quota checks right now? */
export function quotaCheck(options: {
  memberId: string
  classId: string
}): Promise<QuotaCheckResult> {
  const params = new URLSearchParams({
    member_id: options.memberId,
    class_id: options.classId,
  })
  return apiClient.get(`/attendance/quota-check?${params.toString()}`)
}

/**
 * Record a check-in. Staff+. 409 for not-covered / quota-exceeded
 * unless ``override: true`` is set — the UI flow is:
 *   1. Try without override.
 *   2. On 409, show modal.
 *   3. If user confirms, retry with override: true + optional reason.
 */
export function recordEntry(data: RecordEntryRequest): Promise<ClassEntry> {
  return apiClient.post("/attendance", data)
}

/** Soft-delete (undo) an entry. 409 if past the 24h window or already undone. */
export function undoEntry(
  id: string,
  data: UndoEntryRequest,
): Promise<ClassEntry> {
  return apiClient.post(`/attendance/${id}/undo`, data)
}

/**
 * List entries in the caller's tenant with optional filters.
 *
 * Owner audit filters: ``undoneOnly`` and ``overrideOnly`` feed the
 * "mistakes / overrides this week" dashboard views.
 */
export function listEntries(options?: {
  memberId?: string
  classId?: string
  dateFrom?: string // ISO
  dateTo?: string
  includeUndone?: boolean
  undoneOnly?: boolean
  overrideOnly?: boolean
  limit?: number
  offset?: number
}): Promise<ClassEntry[]> {
  const params = new URLSearchParams()
  if (options?.memberId) params.set("member_id", options.memberId)
  if (options?.classId) params.set("class_id", options.classId)
  if (options?.dateFrom) params.set("date_from", options.dateFrom)
  if (options?.dateTo) params.set("date_to", options.dateTo)
  if (options?.includeUndone) params.set("include_undone", "true")
  if (options?.undoneOnly) params.set("undone_only", "true")
  if (options?.overrideOnly) params.set("override_only", "true")
  if (options?.limit !== undefined) params.set("limit", String(options.limit))
  if (options?.offset !== undefined) params.set("offset", String(options.offset))
  const qs = params.toString()
  return apiClient.get(`/attendance${qs ? `?${qs}` : ""}`)
}

/** Full attendance history for one member (newest first). */
export function listMemberEntries(
  memberId: string,
  limit = 50,
): Promise<ClassEntry[]> {
  return apiClient.get(`/attendance/members/${memberId}?limit=${limit}`)
}

/** Per-entitlement usage summary — one row per entitlement on the member's live sub. */
export function memberSummary(
  memberId: string,
): Promise<AttendanceSummaryItem[]> {
  return apiClient.get(`/attendance/members/${memberId}/summary`)
}
