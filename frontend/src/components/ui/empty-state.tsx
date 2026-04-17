import type { ReactNode } from "react"

/**
 * Dashed-border "no items yet" placeholder. Used by list pages when the
 * fetched collection is empty. Keep the message Hebrew; keep the tone
 * gentle (this is usually "you haven't added anything yet", not an error).
 */
export function EmptyState({
  message,
  action,
}: {
  message: string
  /** Optional call-to-action inside the empty state (e.g., "+ Add" button). */
  action?: ReactNode
}) {
  return (
    <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 px-4 py-16 text-center text-sm text-gray-400">
      <div>{message}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
