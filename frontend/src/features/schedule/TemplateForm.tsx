/**
 * TemplateForm — owner creates a recurring rule.
 *
 * On save, the backend materializes 8 weeks of sessions immediately.
 * The week grid populates without a refresh.
 */

import { useCallback, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { listClasses } from "@/features/classes/api"
import type { GymClass } from "@/features/classes/types"
import { listCoaches } from "@/features/coaches/api"
import type { Coach } from "@/features/coaches/types"
import { WeekdaysPicker } from "@/features/coaches/WeekdaysPicker"
import { humanizeScheduleError } from "@/lib/api-errors"
import { useCreateTemplate } from "./hooks"

interface Props {
  onClose: () => void
}

export function TemplateForm({ onClose }: Props) {
  const [cls, setCls] = useState<GymClass | null>(null)
  const [headCoach, setHeadCoach] = useState<Coach | null>(null)
  const [assistantCoach, setAssistantCoach] = useState<Coach | null>(null)
  const [weekdays, setWeekdays] = useState<string[]>(["sun"])
  const [startTime, setStartTime] = useState("18:00")
  const [endTime, setEndTime] = useState("19:00")

  const mutation = useCreateTemplate()

  const loadClasses = useCallback(
    async ({
      search,
      limit,
      offset,
    }: {
      search: string
      limit: number
      offset: number
    }) => {
      const all = await listClasses({ limit: 200, offset, includeInactive: false })
      if (!search) return all.slice(0, limit)
      const lower = search.toLowerCase()
      return all
        .filter((c) => c.name.toLowerCase().includes(lower))
        .slice(0, limit)
    },
    [],
  )
  const loadCoaches = useCallback(
    ({
      search,
      limit,
      offset,
    }: {
      search: string
      limit: number
      offset: number
    }) =>
      listCoaches({
        search: search || undefined,
        status: ["active"],
        limit,
        offset,
      }),
    [],
  )

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!cls || !headCoach || weekdays.length === 0) return
    mutation.mutate(
      {
        class_id: cls.id,
        weekdays,
        start_time: `${startTime}:00`,
        end_time: `${endTime}:00`,
        head_coach_id: headCoach.id,
        assistant_coach_id: assistantCoach?.id ?? null,
      },
      { onSuccess: () => onClose() },
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">תבנית שיעור חוזרת</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              שיעור *
            </label>
            <AsyncCombobox<GymClass>
              value={cls}
              onChange={setCls}
              loadItems={loadClasses}
              getKey={(c) => c.id}
              getLabel={(c) => c.name}
              renderItem={(c) => <span>{c.name}</span>}
              placeholder="בחרו שיעור..."
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              ימי השבוע *
            </label>
            <WeekdaysPicker value={weekdays} onChange={setWeekdays} />
            <p className="mt-1 text-[11px] text-gray-400">
              חובה לבחור לפחות יום אחד.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                שעת התחלה
              </label>
              <input
                type="time"
                required
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                שעת סיום
              </label>
              <input
                type="time"
                required
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              מאמן ראשי *
            </label>
            <AsyncCombobox<Coach>
              value={headCoach}
              onChange={setHeadCoach}
              loadItems={loadCoaches}
              getKey={(c) => c.id}
              getLabel={(c) => `${c.first_name} ${c.last_name}`}
              renderItem={(c) => (
                <span>
                  {c.first_name} {c.last_name}
                </span>
              )}
              placeholder="בחרו מאמן..."
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              מאמן עוזר (לא חובה)
            </label>
            <AsyncCombobox<Coach>
              value={assistantCoach}
              onChange={setAssistantCoach}
              loadItems={loadCoaches}
              getKey={(c) => c.id}
              getLabel={(c) => `${c.first_name} ${c.last_name}`}
              renderItem={(c) => (
                <span>
                  {c.first_name} {c.last_name}
                </span>
              )}
              placeholder="בחרו מאמן..."
            />
          </div>

          {mutation.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {humanizeScheduleError(mutation.error)}
            </div>
          )}

          <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              ביטול
            </button>
            <button
              type="submit"
              disabled={
                !cls ||
                !headCoach ||
                weekdays.length === 0 ||
                mutation.isPending
              }
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? "יוצר..." : "צור תבנית"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
