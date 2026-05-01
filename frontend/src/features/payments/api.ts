import { apiClient } from "@/lib/api-client"
import type {
  Payment,
  PaymentMethod,
  RecordPaymentRequest,
  RefundPaymentRequest,
  RevenueSummary,
} from "./types"

export function listPayments(filters?: {
  memberId?: string
  subscriptionId?: string
  paidFrom?: string
  paidTo?: string
  method?: PaymentMethod
  includeRefunds?: boolean
  limit?: number
  offset?: number
}): Promise<Payment[]> {
  const params = new URLSearchParams()
  if (filters?.memberId) params.set("member_id", filters.memberId)
  if (filters?.subscriptionId) params.set("subscription_id", filters.subscriptionId)
  if (filters?.paidFrom) params.set("paid_from", filters.paidFrom)
  if (filters?.paidTo) params.set("paid_to", filters.paidTo)
  if (filters?.method) params.set("method", filters.method)
  if (filters?.includeRefunds === false) params.set("include_refunds", "false")
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit))
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset))
  const qs = params.toString()
  return apiClient.get(`/payments${qs ? `?${qs}` : ""}`)
}

export function getPayment(id: string): Promise<Payment> {
  return apiClient.get(`/payments/${id}`)
}

export function recordPayment(data: RecordPaymentRequest): Promise<Payment> {
  return apiClient.post("/payments", data)
}

export function refundPayment(
  id: string,
  data: RefundPaymentRequest,
): Promise<Payment> {
  return apiClient.post(`/payments/${id}/refund`, data)
}

export function listMemberPayments(memberId: string): Promise<Payment[]> {
  return apiClient.get(`/members/${memberId}/payments`)
}

export function getRevenueSummary(): Promise<RevenueSummary> {
  return apiClient.get("/dashboard/revenue")
}
