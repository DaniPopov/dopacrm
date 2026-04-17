/**
 * Subscription types — re-exported from the OpenAPI-generated schema.
 *
 * Subscriptions are the commercial link between Members and Plans:
 * "Dana is on the Gold plan at 450₪/mo, cash-paying, expires May 1."
 * Status values: active / frozen / expired / cancelled / replaced.
 */
export type {
  CancelSubscriptionRequest,
  ChangePlanRequest,
  CreateSubscriptionRequest,
  FreezeSubscriptionRequest,
  PaymentMethod,
  RenewSubscriptionRequest,
  Subscription,
  SubscriptionEvent,
  SubscriptionEventType,
  SubscriptionStatus,
} from "@/lib/api-types"
