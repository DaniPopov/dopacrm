import type { SubscriptionStatus } from "./types"

/**
 * Reusable status pill. Shared by the member detail page, the expiring
 * list, and the history table so colors stay consistent across the app.
 *
 * Hebrew labels + the same palette used elsewhere for member status
 * (active = emerald, frozen = amber, expired = slate, cancelled = red).
 * `replaced` is shown in indigo — a distinct color because it's a
 * "history" state, not a terminal-churn state.
 */
const STATUS_META: Record<
  SubscriptionStatus,
  { label: string; className: string }
> = {
  active: {
    label: "פעיל",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  frozen: {
    label: "מוקפא",
    className: "border-amber-200 bg-amber-50 text-amber-700",
  },
  expired: {
    label: "פג תוקף",
    className: "border-slate-200 bg-slate-50 text-slate-600",
  },
  cancelled: {
    label: "בוטל",
    className: "border-red-200 bg-red-50 text-red-700",
  },
  replaced: {
    label: "הוחלף",
    className: "border-indigo-200 bg-indigo-50 text-indigo-700",
  },
}

export function SubscriptionBadge({ status }: { status: SubscriptionStatus }) {
  const meta = STATUS_META[status]
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}
    >
      {meta.label}
    </span>
  )
}
