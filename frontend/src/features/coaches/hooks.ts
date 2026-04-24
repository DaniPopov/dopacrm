import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  assignCoachToClass,
  cancelCoach,
  createCoach,
  deleteClassCoachLink,
  freezeCoach,
  getCoach,
  getCoachEarnings,
  getEarningsSummary,
  inviteCoachUser,
  listClassesForCoach,
  listCoaches,
  listCoachesForClass,
  reassignEntryCoach,
  unfreezeCoach,
  updateClassCoachLink,
  updateCoach,
} from "./api"
import type {
  AssignCoachRequest,
  CoachStatus,
  CreateCoachRequest,
  InviteCoachUserRequest,
  UpdateClassCoachRequest,
  UpdateCoachRequest,
} from "./types"

// ── Queries ────────────────────────────────────────────────────────────

export function useCoaches(filters?: {
  status?: CoachStatus[]
  search?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["coaches", filters ?? {}],
    queryFn: () => listCoaches(filters),
  })
}

export function useCoach(id: string) {
  return useQuery({
    queryKey: ["coaches", id],
    queryFn: () => getCoach(id),
    enabled: !!id,
  })
}

export function useCoachesForClass(classId: string, onlyCurrent = false) {
  return useQuery({
    queryKey: ["class-coaches", classId, { onlyCurrent }],
    queryFn: () => listCoachesForClass(classId, onlyCurrent),
    enabled: !!classId,
  })
}

export function useClassesForCoach(coachId: string, onlyCurrent = false) {
  return useQuery({
    queryKey: ["coaches", coachId, "classes", { onlyCurrent }],
    queryFn: () => listClassesForCoach(coachId, onlyCurrent),
    enabled: !!coachId,
  })
}

export function useCoachEarnings(coachId: string, from: string, to: string) {
  return useQuery({
    queryKey: ["coaches", coachId, "earnings", from, to],
    queryFn: () => getCoachEarnings(coachId, from, to),
    enabled: !!coachId && !!from && !!to,
  })
}

export function useEarningsSummary(from: string, to: string) {
  return useQuery({
    queryKey: ["coaches", "earnings-summary", from, to],
    queryFn: () => getEarningsSummary(from, to),
    enabled: !!from && !!to,
  })
}

// ── Mutations ──────────────────────────────────────────────────────────

export function useCreateCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCoachRequest) => createCoach(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coaches"] }),
  })
}

export function useUpdateCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateCoachRequest }) =>
      updateCoach(id, data),
    onSuccess: (coach) => {
      qc.invalidateQueries({ queryKey: ["coaches"] })
      qc.setQueryData(["coaches", coach.id], coach)
    },
  })
}

export function useFreezeCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => freezeCoach(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coaches"] }),
  })
}

export function useUnfreezeCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unfreezeCoach(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coaches"] }),
  })
}

export function useCancelCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelCoach(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coaches"] }),
  })
}

export function useInviteCoachUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: InviteCoachUserRequest }) =>
      inviteCoachUser(id, data),
    onSuccess: (coach) => {
      qc.invalidateQueries({ queryKey: ["coaches"] })
      qc.setQueryData(["coaches", coach.id], coach)
    },
  })
}

export function useAssignCoachToClass() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ classId, data }: { classId: string; data: AssignCoachRequest }) =>
      assignCoachToClass(classId, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["class-coaches", vars.classId] })
      qc.invalidateQueries({ queryKey: ["coaches"] })
    },
  })
}

export function useUpdateClassCoachLink() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      linkId,
      data,
    }: {
      linkId: string
      data: UpdateClassCoachRequest
    }) => updateClassCoachLink(linkId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["class-coaches"] })
      qc.invalidateQueries({ queryKey: ["coaches"] })
    },
  })
}

export function useDeleteClassCoachLink() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (linkId: string) => deleteClassCoachLink(linkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["class-coaches"] })
      qc.invalidateQueries({ queryKey: ["coaches"] })
    },
  })
}

export function useReassignEntryCoach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, coachId }: { entryId: string; coachId: string | null }) =>
      reassignEntryCoach(entryId, coachId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["attendance"] }),
  })
}
