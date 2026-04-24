/**
 * WeekdaysPicker — 7-button strip for picking which days of the week a
 * coach teaches a class. Shared primitive because the future Schedule
 * feature will want the same look on its calendar filters.
 *
 * Semantics: an empty selection means "every day" (matches the backend
 * attribution rule where ``class_coaches.weekdays = '{}'`` = catch-all).
 * The picker surfaces that explicitly with a "כל הימים" hint when empty.
 */

import { cn } from "@/lib/utils"

const WEEKDAYS = [
  { code: "sun", he: "א" },
  { code: "mon", he: "ב" },
  { code: "tue", he: "ג" },
  { code: "wed", he: "ד" },
  { code: "thu", he: "ה" },
  { code: "fri", he: "ו" },
  { code: "sat", he: "ש" },
] as const

export function WeekdaysPicker({
  value,
  onChange,
  disabled,
}: {
  value: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}) {
  function toggle(code: string) {
    if (disabled) return
    if (value.includes(code)) {
      onChange(value.filter((w) => w !== code))
    } else {
      onChange([...value, code])
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1.5" dir="rtl">
        {WEEKDAYS.map((d) => {
          const selected = value.includes(d.code)
          return (
            <button
              key={d.code}
              type="button"
              onClick={() => toggle(d.code)}
              disabled={disabled}
              aria-pressed={selected}
              aria-label={`יום ${d.he}`}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg border text-sm font-semibold transition-colors disabled:opacity-50",
                selected
                  ? "border-blue-400 bg-blue-50 text-blue-700"
                  : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50",
              )}
            >
              {d.he}
            </button>
          )
        })}
      </div>
      <span className="text-xs text-gray-400">
        {value.length === 0 ? "כל הימים" : `${value.length} ימים נבחרו`}
      </span>
    </div>
  )
}
