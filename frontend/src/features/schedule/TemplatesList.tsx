/**
 * TemplatesList — small inline panel showing the gym's recurring rules.
 *
 * Lets the owner see what's currently scheduled (so they spot duplicate
 * templates etc.) and deactivate any one without leaving the
 * Schedule page. Deactivation also cancels future non-customized
 * sessions, so the calendar cleans up immediately.
 *
 * Lives just below the week navigator. Collapsed by default to keep
 * the calendar real-estate prominent — owner toggles it open when
 * they want to manage templates.
 */

import { useMemo, useState } from "react"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import type { GymClass } from "@/features/classes/types"
import type { Coach } from "@/features/coaches/types"
import { useDeactivateTemplate, useTemplates } from "./hooks"
import type { ScheduleTemplate } from "./types"

interface Props {
  classes: GymClass[]
  coaches: Coach[]
}

export function TemplatesList({ classes, coaches }: Props) {
  const [open, setOpen] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState<ScheduleTemplate | null>(null)
  const { data: templates, isLoading } = useTemplates({ only_active: true })
  const deactivate = useDeactivateTemplate()

  const classMap = useMemo(
    () => new Map(classes.map((c) => [c.id, c])),
    [classes],
  )
  const coachMap = useMemo(
    () => new Map(coaches.map((c) => [c.id, c])),
    [coaches],
  )

  const count = templates?.length ?? 0

  return (
    <div className="mb-4 rounded-xl border border-gray-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-right hover:bg-gray-50"
      >
        <span className="text-sm font-semibold text-gray-700">
          תבניות פעילות{" "}
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
            {count}
          </span>
        </span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-gray-100 p-4">
          {isLoading ? (
            <div className="text-sm text-gray-400">טוען...</div>
          ) : count === 0 ? (
            <div className="text-sm text-gray-400">
              אין תבניות פעילות. לחצו "+ תבנית" כדי ליצור.
            </div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {templates!.map((t) => {
                const cls = classMap.get(t.class_id)
                const coach = coachMap.get(t.head_coach_id)
                return (
                  <li
                    key={t.id}
                    className="flex items-center justify-between py-3 text-sm"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-gray-900">
                        {cls?.name ?? "שיעור"}
                      </div>
                      <div className="text-xs text-gray-500">
                        {(t.weekdays as string[]).map(weekdayHe).join(", ")}{" "}
                        · {t.start_time.slice(0, 5)}–{t.end_time.slice(0, 5)}
                        {coach && (
                          <>
                            {" · "}
                            {coach.first_name} {coach.last_name}
                          </>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => setConfirmRemove(t)}
                      className="ml-2 rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                    >
                      השבת
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}

      {confirmRemove && (
        <ConfirmDialog
          title="השבתת תבנית"
          message="התבנית תושבת ושיעורים עתידיים שטרם נערכו ידנית יבוטלו. לא ניתן לבטל את הפעולה."
          confirmLabel="כן, השבת"
          destructive
          loading={deactivate.isPending}
          onConfirm={() => {
            deactivate.mutate(confirmRemove.id, {
              onSuccess: () => setConfirmRemove(null),
            })
          }}
          onCancel={() => setConfirmRemove(null)}
        />
      )}
    </div>
  )
}

function weekdayHe(code: string): string {
  return (
    {
      sun: "א",
      mon: "ב",
      tue: "ג",
      wed: "ד",
      thu: "ה",
      fri: "ו",
      sat: "ש",
    }[code] ?? code
  )
}
