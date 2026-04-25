/**
 * SessionDetailPanel — modal-ish slide-in panel for one session.
 *
 * Shown when the owner clicks a SessionCard on the WeekGrid. Displays
 * the session header (class + day + time), the coaches, the status,
 * and lets the owner swap coaches or cancel.
 */

import { useCallback, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useAuth } from "@/features/auth/auth-provider"
import { listCoaches } from "@/features/coaches/api"
import type { Coach } from "@/features/coaches/types"
import { humanizeScheduleError } from "@/lib/api-errors"
import { useCancelSession, useUpdateSession } from "./hooks"
import type { ClassSession } from "./types"

interface Props {
  session: ClassSession
  className: string
  headCoach: Coach | null
  assistantCoach: Coach | null
  onClose: () => void
}

export function SessionDetailPanel({
  session,
  className,
  headCoach,
  assistantCoach,
  onClose,
}: Props) {
  const { user } = useAuth()
  const canEdit = user?.role === "owner" || user?.role === "super_admin"
  const cancelMutation = useCancelSession()
  const updateMutation = useUpdateSession()

  const [confirmCancel, setConfirmCancel] = useState(false)
  const [reason, setReason] = useState("")
  const [pendingHeadCoach, setPendingHeadCoach] = useState<Coach | null>(null)

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

  function handleSwap() {
    if (!pendingHeadCoach) return
    updateMutation.mutate(
      { id: session.id, data: { head_coach_id: pendingHeadCoach.id } },
      { onSuccess: () => setPendingHeadCoach(null) },
    )
  }

  function handleCancel() {
    cancelMutation.mutate(
      { id: session.id, data: { reason: reason || null } },
      { onSuccess: () => setConfirmCancel(false) },
    )
  }

  const cancelled = session.status === "cancelled"
  const start = new Date(session.starts_at)
  const end = new Date(session.ends_at)

  return (
    <div
      className="fixed inset-0 z-40 flex items-stretch justify-end bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="relative flex w-full max-w-md flex-col gap-4 overflow-y-auto bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{className}</h2>
            <div className="text-xs text-gray-500" dir="ltr">
              {start.toLocaleString("he-IL")} – {end.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}
            </div>
            {cancelled && (
              <span className="mt-2 inline-flex rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                בוטל
              </span>
            )}
            {session.is_customized && !cancelled && (
              <span className="mt-2 inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                ערוך ידנית
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגור"
          >
            ✕
          </button>
        </div>

        <div className="rounded-lg border border-gray-100 bg-gray-50/50 p-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">מאמן ראשי</h3>
          {headCoach ? (
            <div className="text-sm text-gray-900">
              {headCoach.first_name} {headCoach.last_name}
            </div>
          ) : (
            <div className="text-sm text-gray-400">לא נקבע</div>
          )}
          {canEdit && !cancelled && (
            <div className="mt-3">
              <label className="mb-1 block text-xs font-medium text-gray-700">
                החלף מאמן
              </label>
              <AsyncCombobox<Coach>
                value={pendingHeadCoach}
                onChange={setPendingHeadCoach}
                loadItems={loadCoaches}
                getKey={(c) => c.id}
                getLabel={(c) => `${c.first_name} ${c.last_name}`}
                renderItem={(c) => (
                  <div className="font-medium text-gray-900">
                    {c.first_name} {c.last_name}
                  </div>
                )}
                placeholder="בחרו מאמן..."
              />
              <button
                onClick={handleSwap}
                disabled={!pendingHeadCoach || updateMutation.isPending}
                className="mt-2 w-full rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {updateMutation.isPending ? "שומר..." : "החלף"}
              </button>
            </div>
          )}
        </div>

        {assistantCoach && (
          <div className="rounded-lg border border-gray-100 bg-gray-50/50 p-4">
            <h3 className="mb-2 text-sm font-semibold text-gray-700">
              מאמן עוזר
            </h3>
            <div className="text-sm text-gray-900">
              {assistantCoach.first_name} {assistantCoach.last_name}
            </div>
          </div>
        )}

        {session.notes && (
          <div className="rounded-lg border border-gray-100 bg-gray-50/50 p-4">
            <h3 className="mb-1 text-sm font-semibold text-gray-700">הערות</h3>
            <p className="whitespace-pre-wrap text-sm text-gray-600">
              {session.notes}
            </p>
          </div>
        )}

        {cancelled && session.cancellation_reason && (
          <div className="rounded-lg border border-red-100 bg-red-50/50 p-4">
            <h3 className="mb-1 text-sm font-semibold text-red-700">
              סיבת ביטול
            </h3>
            <p className="text-sm text-red-700">{session.cancellation_reason}</p>
          </div>
        )}

        {(updateMutation.error || cancelMutation.error) && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {humanizeScheduleError(updateMutation.error ?? cancelMutation.error)}
          </div>
        )}

        {canEdit && !cancelled && (
          <button
            onClick={() => setConfirmCancel(true)}
            className="rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50"
          >
            🚫 בטל שיעור זה
          </button>
        )}

        {confirmCancel && (
          <ConfirmDialog
            title="ביטול שיעור"
            message={
              <div className="space-y-2">
                <p>האם לבטל את השיעור?</p>
                <input
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="סיבה (לא חובה)"
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                />
              </div>
            }
            confirmLabel="כן, בטל"
            destructive
            loading={cancelMutation.isPending}
            onConfirm={handleCancel}
            onCancel={() => setConfirmCancel(false)}
          />
        )}
      </div>
    </div>
  )
}
