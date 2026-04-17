import { apiClient } from "@/lib/api-client"
import type {
  CancelSubscriptionRequest,
  ChangePlanRequest,
  CreateSubscriptionRequest,
  FreezeSubscriptionRequest,
  RenewSubscriptionRequest,
  Subscription,
  SubscriptionEvent,
  SubscriptionStatus,
} from "./types"

/**
 * List subscriptions in the caller's tenant. Filterable by member, status,
 * plan, or a "about to expire within N days" window for the dashboard.
 *
 * `GET /api/v1/subscriptions` — tenant-scoped. Any tenant user can read.
 *
 * @throws `ApiError(403)` — caller is super_admin or has no tenant
 */
export function listSubscriptions(options?: {
  memberId?: string
  status?: SubscriptionStatus
  planId?: string
  expiresBefore?: string // YYYY-MM-DD
  expiresWithinDays?: number
  limit?: number
  offset?: number
}): Promise<Subscription[]> {
  const params = new URLSearchParams()
  if (options?.memberId) params.set("member_id", options.memberId)
  if (options?.status) params.set("status", options.status)
  if (options?.planId) params.set("plan_id", options.planId)
  if (options?.expiresBefore) params.set("expires_before", options.expiresBefore)
  if (options?.expiresWithinDays !== undefined) {
    params.set("expires_within_days", String(options.expiresWithinDays))
  }
  if (options?.limit !== undefined) params.set("limit", String(options.limit))
  if (options?.offset !== undefined) params.set("offset", String(options.offset))
  const qs = params.toString()
  return apiClient.get(`/subscriptions${qs ? `?${qs}` : ""}`)
}

/**
 * Fetch one subscription by ID.
 *
 * @throws `ApiError(404)` — sub not found OR in another tenant (no existence leak)
 */
export function getSubscription(id: string): Promise<Subscription> {
  return apiClient.get(`/subscriptions/${id}`)
}

/**
 * Timeline of events for a subscription — created/frozen/unfrozen/renewed/
 * replaced/cancelled/expired. Newest first. System events (nightly jobs)
 * have `created_by = null`.
 */
export function listSubscriptionEvents(id: string): Promise<SubscriptionEvent[]> {
  return apiClient.get(`/subscriptions/${id}/events`)
}

/**
 * Enroll a member in a plan. Staff+.
 *
 * Price is snapshotted from the plan at create time. If the member
 * already has a live (active/frozen) sub, the server rejects with 409.
 *
 * @throws `ApiError(403)` — caller lacks staff+
 * @throws `ApiError(409)` — member has an active sub
 * @throws `ApiError(422)` — invalid input (missing ids, cross-tenant plan, etc.)
 */
export function createSubscription(
  data: CreateSubscriptionRequest,
): Promise<Subscription> {
  return apiClient.post("/subscriptions", data)
}

/**
 * Freeze a subscription. Optional `frozen_until` for auto-unfreeze.
 * Paused time extends expires_at on unfreeze.
 */
export function freezeSubscription(
  id: string,
  data: FreezeSubscriptionRequest,
): Promise<Subscription> {
  return apiClient.post(`/subscriptions/${id}/freeze`, data)
}

/** Unfreeze manually. The service extends expires_at by the frozen duration. */
export function unfreezeSubscription(id: string): Promise<Subscription> {
  return apiClient.post(`/subscriptions/${id}/unfreeze`)
}

/**
 * Renew a subscription — pushes expires_at forward. Default extension is
 * the plan's billing period; `new_expires_at` lets staff override for
 * "paid for 2 months" cases. Works on both `active` AND `expired` subs —
 * the latter rescues a lapsed member on the same row with days_late logged.
 */
export function renewSubscription(
  id: string,
  data: RenewSubscriptionRequest,
): Promise<Subscription> {
  return apiClient.post(`/subscriptions/${id}/renew`, data)
}

/**
 * Change plan (upgrade / downgrade). Old sub becomes `replaced` (NOT
 * cancelled — different for reports), new sub is active with a fresh
 * price snapshot from the new plan. Returns the NEW sub.
 *
 * @throws `ApiError(409)` — `new_plan_id` equals the current plan id
 */
export function changePlan(
  id: string,
  data: ChangePlanRequest,
): Promise<Subscription> {
  return apiClient.post(`/subscriptions/${id}/change-plan`, data)
}

/**
 * Cancel (hard-terminal). Optional canonical `reason` + free-text `detail`
 * feed the churn-analytics dashboard. Rejoin = new sub.
 */
export function cancelSubscription(
  id: string,
  data: CancelSubscriptionRequest,
): Promise<Subscription> {
  return apiClient.post(`/subscriptions/${id}/cancel`, data)
}
