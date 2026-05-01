import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  getPayment,
  getRevenueSummary,
  listMemberPayments,
  listPayments,
  recordPayment,
  refundPayment,
} from "./api"
import type {
  PaymentMethod,
  RecordPaymentRequest,
  RefundPaymentRequest,
} from "./types"

// ── Queries ─────────────────────────────────────────────────────────

export function usePayments(filters?: {
  memberId?: string
  subscriptionId?: string
  paidFrom?: string
  paidTo?: string
  method?: PaymentMethod
  includeRefunds?: boolean
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["payments", filters ?? {}],
    queryFn: () => listPayments(filters),
  })
}

export function usePayment(id: string) {
  return useQuery({
    queryKey: ["payments", id],
    queryFn: () => getPayment(id),
    enabled: !!id,
  })
}

export function useMemberPayments(memberId: string) {
  return useQuery({
    queryKey: ["payments", "member", memberId],
    queryFn: () => listMemberPayments(memberId),
    enabled: !!memberId,
  })
}

export function useRevenueSummary() {
  return useQuery({
    queryKey: ["payments", "revenue-summary"],
    queryFn: getRevenueSummary,
  })
}

// ── Mutations ───────────────────────────────────────────────────────

function invalidateAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["payments"] })
}

export function useRecordPayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: RecordPaymentRequest) => recordPayment(data),
    onSuccess: () => invalidateAll(qc),
  })
}

export function useRefundPayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RefundPaymentRequest }) =>
      refundPayment(id, data),
    onSuccess: () => invalidateAll(qc),
  })
}
