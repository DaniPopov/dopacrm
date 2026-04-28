import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  addActivity,
  assignLead,
  convertLead,
  createLead,
  getLead,
  getLeadStats,
  listActivities,
  listLeads,
  listLostReasons,
  setLeadStatus,
  updateLead,
} from "./api"
import type {
  AddActivityRequest,
  AssignLeadRequest,
  ConvertLeadRequest,
  CreateLeadRequest,
  LeadSource,
  LeadStatus,
  SetLeadStatusRequest,
  UpdateLeadRequest,
} from "./types"

// ── Queries ─────────────────────────────────────────────────────────

export function useLeads(filters?: {
  status?: LeadStatus[]
  source?: LeadSource[]
  assignedTo?: string
  search?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["leads", filters ?? {}],
    queryFn: () => listLeads(filters),
  })
}

export function useLead(id: string) {
  return useQuery({
    queryKey: ["leads", id],
    queryFn: () => getLead(id),
    enabled: !!id,
  })
}

export function useLeadActivities(leadId: string) {
  return useQuery({
    queryKey: ["leads", leadId, "activities"],
    queryFn: () => listActivities(leadId),
    enabled: !!leadId,
  })
}

export function useLeadStats() {
  return useQuery({
    queryKey: ["leads", "stats"],
    queryFn: getLeadStats,
  })
}

export function useLostReasons(opts?: { days?: number; limit?: number }) {
  return useQuery({
    queryKey: ["leads", "lost-reasons", opts ?? {}],
    queryFn: () => listLostReasons(opts),
  })
}

// ── Mutations ───────────────────────────────────────────────────────

function invalidateAllLeadQueries(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["leads"] })
}

export function useCreateLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateLeadRequest) => createLead(data),
    onSuccess: () => invalidateAllLeadQueries(qc),
  })
}

export function useUpdateLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateLeadRequest }) =>
      updateLead(id, data),
    onSuccess: (lead) => {
      invalidateAllLeadQueries(qc)
      qc.setQueryData(["leads", lead.id], lead)
    },
  })
}

export function useSetLeadStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SetLeadStatusRequest }) =>
      setLeadStatus(id, data),
    onSuccess: (lead) => {
      invalidateAllLeadQueries(qc)
      qc.setQueryData(["leads", lead.id], lead)
    },
  })
}

export function useAssignLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: AssignLeadRequest }) =>
      assignLead(id, data),
    onSuccess: (lead) => {
      invalidateAllLeadQueries(qc)
      qc.setQueryData(["leads", lead.id], lead)
    },
  })
}

export function useConvertLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConvertLeadRequest }) =>
      convertLead(id, data),
    onSuccess: (result) => {
      invalidateAllLeadQueries(qc)
      qc.setQueryData(["leads", result.lead.id], result.lead)
      // The new member + sub may also be in caches.
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.invalidateQueries({ queryKey: ["subscriptions"] })
    },
  })
}

export function useAddActivity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: AddActivityRequest }) =>
      addActivity(id, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["leads", vars.id, "activities"] })
    },
  })
}
