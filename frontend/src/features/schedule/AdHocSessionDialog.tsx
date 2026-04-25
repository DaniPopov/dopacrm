/**
 * AdHocSessionDialog — one-off session that doesn't follow a template.
 *
 * Visiting trainer special workshop, makeup classes, etc. The created
 * session is automatically marked is_customized=true so it never
 * gets touched by template re-materialization.
 */

import { useCallback, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { listClasses } from "@/features/classes/api"
import type { GymClass } from "@/features/classes/types"
import { listCoaches } from "@/features/coaches/api"
import type { Coach } from "@/features/coaches/types"
import { humanizeScheduleError } from "@/lib/api-errors"
import { useCreateAdHocSession } from "./hooks"

interface Props {
  defaultDate?: Date
  onClose: () => void
}

export function AdHocSessionDialog({ defaultDate, onClose }: Props) {
  const [cls, setCls] = useState<GymClass | null>(null)
  const [coach, setCoach] = useState<Coach | null>(null)
  const [date, setDate] = useState(formatDateInput(defaultDate ?? new Date()))
  const [startTime, setStartTime] = useState("18:00")
  const [endTime, setEndTime] = useState("19:00")
  const [notes, setNotes] = useState("")

  const mutation = useCreateAdHocSession()

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
    if (!cls) return
    const startsAt = new Date(`${date}T${startTime}:00`)
    const endsAt = new Date(`${date}T${endTime}:00`)
    mutation.mutate(
      {
        class_id: cls.id,
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        head_coach_id: coach?.id ?? null,
        assistant_coach_id: null,
        notes: notes || null,
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
          <h3 className="text-lg font-bold text-gray-900">שיעור חד-פעמי</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              שיעור
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

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                תאריך
              </label>
              <input
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                התחלה
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
                סיום
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
              מאמן ראשי
            </label>
            <AsyncCombobox<Coach>
              value={coach}
              onChange={setCoach}
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
              הערות (לא חובה)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className={inputClass}
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
              disabled={!cls || mutation.isPending}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? "שומר..." : "צור שיעור"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

function formatDateInput(d: Date): string {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, "0")
  const dd = String(d.getDate()).padStart(2, "0")
  return `${yyyy}-${mm}-${dd}`
}
