import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  cancelSubscription,
  changePlan,
  createSubscription,
  freezeSubscription,
  getSubscription,
  listSubscriptionEvents,
  listSubscriptions,
  renewSubscription,
  unfreezeSubscription,
} from "./api"
import type {
  CancelSubscriptionRequest,
  ChangePlanRequest,
  CreateSubscriptionRequest,
  FreezeSubscriptionRequest,
  RenewSubscriptionRequest,
  SubscriptionStatus,
} from "./types"

/**
 * Invalidate every subscription-sensitive cache after a mutation.
 *
 * Sub mutations move Member.status too, so the member list / detail pages
 * must refetch as well. We invalidate both top-level keys.
 */
function invalidateAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["subscriptions"] })
  qc.invalidateQueries({ queryKey: ["members"] })
}

/** List subscriptions in the caller's tenant with optional filters. */
export function useSubscriptions(filters?: {
  memberId?: string
  status?: SubscriptionStatus
  planId?: string
  expiresBefore?: string
  expiresWithinDays?: number
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["subscriptions", filters ?? {}],
    queryFn: () => listSubscriptions(filters),
  })
}

/** Fetch one sub. Query key: `["subscriptions", id]`. Disabled when id is empty. */
export function useSubscription(id: string) {
  return useQuery({
    queryKey: ["subscriptions", id],
    queryFn: () => getSubscription(id),
    enabled: !!id,
  })
}

/** Subscription event timeline (newest first). */
export function useSubscriptionEvents(id: string) {
  return useQuery({
    queryKey: ["subscriptions", id, "events"],
    queryFn: () => listSubscriptionEvents(id),
    enabled: !!id,
  })
}

/**
 * Convenience for the member detail page: fetch the member's current
 * (active/frozen) sub in a single query. Implementation: list filtered by
 * memberId; current sub is whichever row is in status ∈ {active, frozen}.
 * Returns `null` if none.
 */
export function useCurrentSubscriptionForMember(memberId: string) {
  return useQuery({
    queryKey: ["subscriptions", { memberId, live: true }],
    queryFn: async () => {
      const all = await listSubscriptions({ memberId })
      return (
        all.find((s) => s.status === "active" || s.status === "frozen") ?? null
      )
    },
    enabled: !!memberId,
  })
}

/**
 * Full subscription history for one member (newest first). Used by the
 * member detail page's history section.
 */
export function useSubscriptionHistoryForMember(memberId: string) {
  return useQuery({
    queryKey: ["subscriptions", { memberId, history: true }],
    queryFn: () => listSubscriptions({ memberId }),
    enabled: !!memberId,
  })
}

/** Enroll a member in a plan. Invalidates subs + members on success. */
export function useCreateSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateSubscriptionRequest) => createSubscription(data),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useFreezeSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FreezeSubscriptionRequest }) =>
      freezeSubscription(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useUnfreezeSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unfreezeSubscription(id),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useRenewSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RenewSubscriptionRequest }) =>
      renewSubscription(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useChangePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ChangePlanRequest }) =>
      changePlan(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useCancelSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CancelSubscriptionRequest }) =>
      cancelSubscription(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}
