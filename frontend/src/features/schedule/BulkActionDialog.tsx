/**
 * BulkActionDialog — "cancel/swap every boxing session from Mar 1 to
 * Mar 14" flow. The vacation-handling power-tool.
 *
 * Three inputs:
 * - Class (AsyncCombobox)
 * - Date range (from, to)
 * - Action (cancel | swap_coach), with a coach picker when swap.
 *
 * Submits to POST /api/v1/schedule/bulk-action and shows a summary on
 * success ("3 sessions cancelled").
 */

import { useCallback, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { listClasses } from "@/features/classes/api"
import type { GymClass } from "@/features/classes/types"
import { listCoaches } from "@/features/coaches/api"
import type { Coach } from "@/features/coaches/types"
import { humanizeScheduleError } from "@/lib/api-errors"
import { useBulkAction } from "./hooks"

type Action = "cancel" | "swap_coach"

interface Props {
  onClose: () => void
}

export function BulkActionDialog({ onClose }: Props) {
  const [cls, setCls] = useState<GymClass | null>(null)
  const [from, setFrom] = useState<string>("")
  const [to, setTo] = useState<string>("")
  const [action, setAction] = useState<Action>("cancel")
  const [coach, setCoach] = useState<Coach | null>(null)
  const [reason, setReason] = useState("")

  const mutation = useBulkAction()

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
      // listClasses doesn't accept a server-side search param yet; pull
      // a generous page and filter client-side. Gym class catalogs are
      // small enough (typically <50) that this is fine.
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
    ({ search, limit, offset }: { search: string; limit: number; offset: number }) =>
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
    if (!cls || !from || !to) return
    mutation.mutate(
      {
        class_id: cls.id,
        from,
        to,
        action,
        new_coach_id: action === "swap_coach" ? coach?.id ?? null : null,
        reason: reason || null,
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
          <h3 className="text-lg font-bold text-gray-900">פעולה לטווח תאריכים</h3>
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

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                מתאריך
              </label>
              <input
                type="date"
                required
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                עד תאריך
              </label>
              <input
                type="date"
                required
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              פעולה
            </label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as Action)}
              className={inputClass}
            >
              <option value="cancel">בטל את כל השיעורים בטווח</option>
              <option value="swap_coach">החלף מאמן ראשי לכל השיעורים</option>
            </select>
          </div>

          {action === "swap_coach" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                מאמן חדש
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
          )}

          {action === "cancel" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                סיבה (לא חובה)
              </label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className={inputClass}
              />
            </div>
          )}

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
                mutation.isPending ||
                !cls ||
                !from ||
                !to ||
                (action === "swap_coach" && !coach)
              }
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? "מבצע..." : "בצע"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
