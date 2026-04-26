/**
 * BulkActionDialog — "cancel/swap every boxing session from Mar 1 to
 * Mar 14" flow. The vacation-handling power-tool.
 *
 * Substitute-pay flow: when action=swap_coach and the picked
 * substitute has no existing class_coaches link for the class, the
 * dialog reveals a "How should this substitute be paid?" inline form
 * (required). Submits as substitute_pay_model + substitute_pay_amount_cents
 * — backend auto-creates a temp class_coaches link covering the range
 * so the substitute earns correctly.
 */

import { useCallback, useMemo, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { listClasses } from "@/features/classes/api"
import type { GymClass } from "@/features/classes/types"
import { listCoaches } from "@/features/coaches/api"
import { useCoachesForClass } from "@/features/coaches/hooks"
import type { Coach, PayModel } from "@/features/coaches/types"
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
  // Substitute pay (only filled when needed).
  const [subPayModel, setSubPayModel] = useState<PayModel>("per_session")
  const [subPayAmount, setSubPayAmount] = useState<number>(30)

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

  // When action=swap_coach + class+coach are picked, look up existing
  // links to detect if the substitute needs a pay rate.
  const { data: classCoachLinks } = useCoachesForClass(cls?.id ?? "", false)
  const subHasRateForRange = useMemo(() => {
    if (!cls || !coach || action !== "swap_coach") return true
    if (!classCoachLinks || !from || !to) return true
    const fromD = from
    const toD = to
    return classCoachLinks.some(
      (l) =>
        l.coach_id === coach.id &&
        l.starts_on <= toD &&
        (l.ends_on === null || l.ends_on >= fromD),
    )
  }, [cls, coach, action, classCoachLinks, from, to])

  const needsSubPay =
    action === "swap_coach" && coach !== null && !subHasRateForRange

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!cls || !from || !to) return
    if (action === "swap_coach" && !coach) return
    mutation.mutate(
      {
        class_id: cls.id,
        from,
        to,
        action,
        new_coach_id: action === "swap_coach" ? coach?.id ?? null : null,
        reason: reason || null,
        substitute_pay_model: needsSubPay ? subPayModel : null,
        substitute_pay_amount_cents: needsSubPay
          ? Math.max(0, Math.round(subPayAmount * 100))
          : null,
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

          {/* Substitute pay — only shown when needed */}
          {needsSubPay && (
            <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/40 p-4">
              <div className="text-xs text-amber-900">
                למאמן זה אין תעריף עבור השיעור הזה. הגדירו תעריף זמני
                לתקופת ההחלפה — נוצר אוטומטית עבור הטווח שבחרתם בלבד.
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">
                    מודל תשלום
                  </label>
                  <select
                    value={subPayModel}
                    onChange={(e) => setSubPayModel(e.target.value as PayModel)}
                    className={inputClass}
                  >
                    <option value="fixed">משכורת קבועה (חודשית)</option>
                    <option value="per_session">לפי שיעור</option>
                    <option value="per_attendance">לפי כניסה</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">
                    {subPayModel === "fixed"
                      ? "סכום חודשי (₪)"
                      : "סכום ליחידה (₪)"}
                  </label>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={subPayAmount}
                    onChange={(e) =>
                      setSubPayAmount(Number(e.target.value) || 0)
                    }
                    className={inputClass}
                    dir="ltr"
                  />
                </div>
              </div>
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
