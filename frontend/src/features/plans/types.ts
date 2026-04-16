/**
 * Membership plan types — re-exported from the OpenAPI-generated schema.
 *
 * A plan has a header (name/price/billing_period) and 0..N entitlements.
 * Zero entitlements = unlimited access to any class; one or more rows
 * narrow access per-class with a quota + reset cadence.
 */
export type {
  BillingPeriod,
  CreatePlanRequest,
  MembershipPlan,
  PlanEntitlement,
  PlanEntitlementInput,
  PlanType,
  ResetPeriod,
  UpdatePlanRequest,
} from "@/lib/api-types"
