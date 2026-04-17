import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
import type { SubscriptionStatus } from "./types"

/**
 * Subscription-specific wrapper around the shared ``StatusBadge``. Keeps
 * the Hebrew labels + variant mapping local to the domain (other pages
 * that happen to show a subscription status see the same colors as the
 * member/plan/tenant status pills).
 *
 * Variant choices:
 *   active    → success (paid-up & live)
 *   frozen    → warning (paused, needs attention)
 *   expired   → neutral (lapsed, renewable)
 *   cancelled → danger  (actively left)
 *   replaced  → info    (history / chain-link)
 */
const STATUS_META: Record<
  SubscriptionStatus,
  { label: string; variant: StatusVariant }
> = {
  active: { label: "פעיל", variant: "success" },
  frozen: { label: "מוקפא", variant: "warning" },
  expired: { label: "פג תוקף", variant: "neutral" },
  cancelled: { label: "בוטל", variant: "danger" },
  replaced: { label: "הוחלף", variant: "info" },
}

export function SubscriptionBadge({ status }: { status: SubscriptionStatus }) {
  const meta = STATUS_META[status]
  return <StatusBadge variant={meta.variant}>{meta.label}</StatusBadge>
}
