/**
 * ClassCoachesSection — "Coaches" panel embedded on a class detail page.
 *
 * Used on ``/classes/:id`` for the owner to attach/remove coaches, pick
 * their role + pay model, and see the current weekday pattern at a
 * glance. Reuses ``AsyncCombobox`` to pick the coach, ``WeekdaysPicker``
 * for the day strip.
 */

import { useCallback, useState } from "react"
import { AsyncCombobox } from "@/components/ui/async-combobox"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { SectionCard } from "@/components/ui/section-card"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeCoachError } from "@/lib/api-errors"
import { formatMoney, payModelLabel } from "./EarningsCard"
import {
  useAssignCoachToClass,
  useCoach,
  useCoachesForClass,
  useDeleteClassCoachLink,
} from "./hooks"
import { listCoaches } from "./api"
import { WeekdaysPicker } from "./WeekdaysPicker"
import type { Coach, ClassCoach, PayModel } from "./types"

export default function ClassCoachesSection({ classId }: { classId: string }) {
  const { user } = useAuth()
  const canEdit = user?.role === "owner" || user?.role === "super_admin"
  const { data: links, isLoading } = useCoachesForClass(classId, false)
  const [adding, setAdding] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<ClassCoach | null>(null)
  const del = useDeleteClassCoachLink()

  return (
    <SectionCard
      title="מאמנים"
      action={
        canEdit && !adding ? (
          <button
            onClick={() => setAdding(true)}
            className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
          >
            + הוסף מאמן
          </button>
        ) : null
      }
    >
      {adding && (
        <AssignCoachForm
          classId={classId}
          onDone={() => setAdding(false)}
          onCancel={() => setAdding(false)}
        />
      )}

      {isLoading ? (
        <div className="text-sm text-gray-400">טוען...</div>
      ) : !links || links.length === 0 ? (
        <div className="text-sm text-gray-400">
          אין מאמנים משויכים. {canEdit && 'לחצו "הוסף מאמן" כדי לשייך.'}
        </div>
      ) : (
        <ul className="divide-y divide-gray-100">
          {links.map((link) => (
            <li key={link.id} className="py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <CoachNameChip coachId={link.coach_id} />
                    {link.is_primary && (
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
                        ראשי
                      </span>
                    )}
                    <span className="text-xs text-gray-400">{link.role}</span>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {payModelLabel(link.pay_model)} ·{" "}
                    <span dir="ltr">
                      {formatMoney(link.pay_amount_cents, "ILS")}
                    </span>{" "}
                    ·{" "}
                    {link.weekdays.length === 0
                      ? "כל הימים"
                      : link.weekdays.join(", ")}
                  </div>
                </div>
                {canEdit && (
                  <button
                    onClick={() => setConfirmDelete(link)}
                    className="rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                  >
                    הסרה
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="הסרת מאמן"
          message="להסיר את שיוך המאמן לשיעור זה? היסטוריית הכניסות נשמרת."
          confirmLabel="הסר"
          destructive
          loading={del.isPending}
          onConfirm={() => {
            del.mutate(confirmDelete.id, {
              onSuccess: () => setConfirmDelete(null),
            })
          }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </SectionCard>
  )
}

/* ── Assign form ────────────────────────────────────────────────────── */

function AssignCoachForm({
  classId,
  onDone,
  onCancel,
}: {
  classId: string
  onDone: () => void
  onCancel: () => void
}) {
  const assign = useAssignCoachToClass()
  const [coach, setCoach] = useState<Coach | null>(null)
  const [role, setRole] = useState("ראשי")
  const [isPrimary, setIsPrimary] = useState(true)
  const [payModel, setPayModel] = useState<PayModel>("per_attendance")
  const [amount, setAmount] = useState<number>(30)
  const [weekdays, setWeekdays] = useState<string[]>([])

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
    if (!coach) return
    assign.mutate(
      {
        classId,
        data: {
          coach_id: coach.id,
          role: role.trim() || "ראשי",
          is_primary: isPrimary,
          pay_model: payModel,
          pay_amount_cents: Math.max(0, Math.round(amount * 100)),
          weekdays,
        },
      },
      {
        onSuccess: () => {
          onDone()
        },
      },
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-4 rounded-lg border border-blue-200 bg-blue-50/30 p-4"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="mb-1 block text-xs font-medium text-gray-700">
            מאמן *
          </label>
          <AsyncCombobox<Coach>
            value={coach}
            onChange={setCoach}
            loadItems={loadCoaches}
            getKey={(c) => c.id}
            getLabel={(c) => `${c.first_name} ${c.last_name}`}
            renderItem={(c) => (
              <div>
                <div className="font-medium text-gray-900">
                  {c.first_name} {c.last_name}
                </div>
                {c.phone && (
                  <div className="text-xs text-gray-400" dir="ltr">
                    {c.phone}
                  </div>
                )}
              </div>
            )}
            placeholder="חפשו מאמן..."
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            תפקיד
          </label>
          <input
            type="text"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className={inputClass}
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            מודל תשלום
          </label>
          <select
            value={payModel}
            onChange={(e) => setPayModel(e.target.value as PayModel)}
            className={inputClass}
          >
            <option value="fixed">משכורת קבועה (חודשית)</option>
            <option value="per_session">לפי שיעור</option>
            <option value="per_attendance">לפי כניסה</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            {payModel === "fixed" ? "סכום חודשי (₪)" : "סכום ליחידה (₪)"}
          </label>
          <input
            type="number"
            min={0}
            step={1}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value) || 0)}
            className={inputClass}
            dir="ltr"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            ימי לימוד
          </label>
          <WeekdaysPicker value={weekdays} onChange={setWeekdays} />
        </div>

        <div className="flex items-end">
          <label className="inline-flex items-center gap-2 text-xs text-gray-700">
            <input
              type="checkbox"
              checked={isPrimary}
              onChange={(e) => setIsPrimary(e.target.checked)}
            />
            מאמן ראשי (מקבל קרדיט עבור כניסה)
          </label>
        </div>
      </div>

      {assign.error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {humanizeCoachError(assign.error)}
        </div>
      )}

      <div className="mt-4 flex justify-end gap-3 border-t border-blue-100 pt-3">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 px-4 py-1.5 text-sm font-medium text-gray-600 hover:bg-white"
        >
          ביטול
        </button>
        <button
          type="submit"
          disabled={!coach || assign.isPending}
          className="rounded-lg bg-blue-600 px-5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {assign.isPending ? "שומר..." : "שייך"}
        </button>
      </div>
    </form>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

/* ── Coach name chip ────────────────────────────────────────────────── */

function CoachNameChip({ coachId }: { coachId: string }) {
  const { data: coach } = useCoach(coachId)
  return (
    <span className="font-medium text-gray-900">
      {coach ? `${coach.first_name} ${coach.last_name}` : "מאמן"}
    </span>
  )
}
