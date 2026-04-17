import type { ReactNode } from "react"

/**
 * Generic status pill. Single source for the semantic color palette used
 * across members / subscriptions / plans / classes / tenants.
 *
 * Use one of the named variants instead of inlining Tailwind classes —
 * that way a color-palette tweak stays a one-file change.
 *
 * If a domain has its own mapping (e.g., `SubscriptionBadge`), that
 * component can delegate here by picking the right variant.
 */
export type StatusVariant =
  | "success" // פעיל / approved / paid
  | "warning" // frozen / pending / about-to-expire
  | "danger" // cancelled / failed
  | "neutral" // expired / archived / read-only
  | "info" // replaced / history / chain-link
  | "primary" // trial / new / highlighted

const VARIANTS: Record<StatusVariant, string> = {
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  danger: "border-red-200 bg-red-50 text-red-700",
  neutral: "border-slate-200 bg-slate-50 text-slate-600",
  info: "border-indigo-200 bg-indigo-50 text-indigo-700",
  primary: "border-blue-200 bg-blue-50 text-blue-700",
}

export function StatusBadge({
  variant,
  children,
}: {
  variant: StatusVariant
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${VARIANTS[variant]}`}
    >
      {children}
    </span>
  )
}
