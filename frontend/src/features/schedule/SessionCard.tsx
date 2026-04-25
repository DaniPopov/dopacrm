/**
 * SessionCard — one cell in the week grid.
 *
 * Renders a class name + coach name + a small status indicator. Uses
 * the class's color (passed from the page) so cancelled sessions get
 * a strikethrough + 🚫 marker, ad-hoc sessions get a ★ badge.
 */

import { cn } from "@/lib/utils"
import type { ClassSession } from "./types"

interface Props {
  session: ClassSession
  className: string
  classColor: string | null
  coachName: string | null
  onClick: () => void
}

export function SessionCard({
  session,
  className,
  classColor,
  coachName,
  onClick,
}: Props) {
  const cancelled = session.status === "cancelled"
  const adhoc = session.template_id === null

  // Use class color to tint the card; fall back to neutral gray.
  const tint = classColor ?? "#e5e7eb"
  const start = new Date(session.starts_at)
  const end = new Date(session.ends_at)
  const timeLabel = `${formatTime(start)}–${formatTime(end)}`

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex h-full w-full flex-col gap-0.5 rounded-md border-2 p-1.5 text-right transition-all",
        "hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500/40",
        cancelled
          ? "border-gray-300 bg-gray-50 opacity-60"
          : "border-transparent",
      )}
      style={
        cancelled
          ? undefined
          : {
              backgroundColor: `${tint}22`,
              borderColor: `${tint}66`,
            }
      }
    >
      <div className="flex items-center justify-between gap-1">
        <span
          className={cn(
            "truncate text-xs font-semibold",
            cancelled ? "text-gray-500 line-through" : "text-gray-900",
          )}
        >
          {className}
        </span>
        {cancelled && <span aria-label="cancelled">🚫</span>}
        {adhoc && !cancelled && (
          <span
            className="rounded-full bg-amber-100 px-1.5 text-[9px] font-medium text-amber-700"
            title="ad-hoc"
          >
            ★
          </span>
        )}
      </div>
      <div className="truncate text-[11px] text-gray-600">
        {coachName ?? <span className="text-gray-400">ללא מאמן</span>}
      </div>
      <div
        className="font-mono text-[10px] text-gray-500"
        dir="ltr"
      >
        {timeLabel}
      </div>
    </button>
  )
}

function formatTime(d: Date): string {
  const hh = d.getHours().toString().padStart(2, "0")
  const mm = d.getMinutes().toString().padStart(2, "0")
  return `${hh}:${mm}`
}
