import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  listEntries,
  listMemberEntries,
  memberSummary,
  quotaCheck,
  recordEntry,
  undoEntry,
} from "./api"
import type { RecordEntryRequest, UndoEntryRequest } from "./types"

/**
 * Invalidate every attendance-sensitive cache after a mutation.
 * Entries change what ``quotaCheck`` would return, what the summary
 * shows, and the list pages — flush them all.
 */
function invalidateAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["attendance"] })
}

/** List attendance entries with filters (owner dashboards + audit). */
export function useAttendanceList(filters?: Parameters<typeof listEntries>[0]) {
  return useQuery({
    queryKey: ["attendance", "list", filters ?? {}],
    queryFn: () => listEntries(filters),
  })
}

/** Full history for one member. */
export function useMemberAttendance(memberId: string) {
  return useQuery({
    queryKey: ["attendance", "member", memberId],
    queryFn: () => listMemberEntries(memberId),
    enabled: !!memberId,
  })
}

/** Per-entitlement usage summary — drives the check-in header. */
export function useMemberAttendanceSummary(memberId: string) {
  return useQuery({
    queryKey: ["attendance", "summary", memberId],
    queryFn: () => memberSummary(memberId),
    enabled: !!memberId,
  })
}

/**
 * Quota peek for ONE (member, class) pair.
 *
 * Not strictly needed for the UI since the summary covers it, but
 * useful if a future feature needs a fresh check before recording.
 */
export function useQuotaCheck(memberId: string, classId: string, enabled = true) {
  return useQuery({
    queryKey: ["attendance", "quota-check", memberId, classId],
    queryFn: () => quotaCheck({ memberId, classId }),
    enabled: enabled && !!memberId && !!classId,
  })
}

/** Record a check-in. */
export function useRecordEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: RecordEntryRequest) => recordEntry(data),
    onSuccess: () => invalidateAll(qc),
  })
}

/** Undo a check-in (within 24h). */
export function useUndoEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UndoEntryRequest }) =>
      undoEntry(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}
