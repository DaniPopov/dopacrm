import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  cancelMember,
  createMember,
  freezeMember,
  getMember,
  listMembers,
  unfreezeMember,
  updateMember,
} from "./api"
import type {
  CreateMemberRequest,
  MemberStatus,
  UpdateMemberRequest,
} from "./types"

/** Fetch members for the caller's tenant with optional filters. */
export function useMembers(filters?: {
  status?: MemberStatus[]
  search?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["members", filters ?? {}],
    queryFn: () => listMembers(filters),
  })
}

/** Fetch one member. Query key: `["members", id]`. */
export function useMember(id: string) {
  return useQuery({
    queryKey: ["members", id],
    queryFn: () => getMember(id),
    enabled: !!id,
  })
}

/** Create a member. Invalidates every members list + tenant stats. */
export function useCreateMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateMemberRequest) => createMember(data),
    onSuccess: (member) => {
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.invalidateQueries({ queryKey: ["tenants", member.tenant_id, "stats"] })
    },
  })
}

/** Update a member. Invalidates lists + the single-member cache. */
export function useUpdateMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateMemberRequest }) =>
      updateMember(id, data),
    onSuccess: (member) => {
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.setQueryData(["members", member.id], member)
    },
  })
}

/** Freeze. Invalidates lists + stats (active count changes). */
export function useFreezeMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, until }: { id: string; until?: string }) =>
      freezeMember(id, until),
    onSuccess: (member) => {
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.invalidateQueries({ queryKey: ["tenants", member.tenant_id, "stats"] })
    },
  })
}

/** Unfreeze. Invalidates lists + stats. */
export function useUnfreezeMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unfreezeMember(id),
    onSuccess: (member) => {
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.invalidateQueries({ queryKey: ["tenants", member.tenant_id, "stats"] })
    },
  })
}

/** Cancel (terminal). Invalidates lists + stats. */
export function useCancelMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelMember(id),
    onSuccess: (member) => {
      qc.invalidateQueries({ queryKey: ["members"] })
      qc.invalidateQueries({ queryKey: ["tenants", member.tenant_id, "stats"] })
    },
  })
}
