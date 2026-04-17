import { useState, type FormEvent } from "react"
import { usePlans } from "@/features/plans/hooks"
import { humanizeSubscriptionError } from "@/lib/api-errors"
import { useCreateSubscription } from "./hooks"

/**
 * Enroll a member in a plan.
 *
 * Opened from the member detail page when the member has no current sub.
 * Fields: plan (required, dropdown of active plans), started_at (default
 * today, future dates allowed), expires_at (optional — leave empty for
 * card-auto, set a date for cash/prepaid).
 */
export default function SubscriptionEnrollDialog({
  memberId,
  onClose,
  onSuccess,
}: {
  memberId: string
  onClose: () => void
  onSuccess?: () => void
}) {
  const { data: plans, isLoading: plansLoading } = usePlans()
  const create = useCreateSubscription()

  const [planId, setPlanId] = useState("")
  const [startedAt, setStartedAt] = useState("")
  const [expiresAt, setExpiresAt] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!planId) return
    create.mutate(
      {
        member_id: memberId,
        plan_id: planId,
        started_at: startedAt || null,
        expires_at: expiresAt || null,
      },
      {
        onSuccess: () => {
          create.reset()
          onSuccess?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal onClose={onClose} title="רישום מנוי חדש">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="מסלול *">
          {plansLoading ? (
            <div className="text-sm text-gray-400">טוען מסלולים...</div>
          ) : (
            <select
              required
              value={planId}
              onChange={(e) => setPlanId(e.target.value)}
              className={inputClass}
            >
              <option value="">בחרו מסלול</option>
              {plans?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {(p.price_cents / 100).toLocaleString("he-IL")} ₪
                </option>
              ))}
            </select>
          )}
        </Field>

        <Field
          label="תאריך התחלה"
          helper="השאירו ריק להיום. ניתן להזין תאריך עתידי"
        >
          <input
            type="date"
            value={startedAt}
            onChange={(e) => setStartedAt(e.target.value)}
            className={inputClass}
          />
        </Field>

        <Field
          label="תוקף עד"
          helper={
            "תשלום במזומן: הזינו תאריך התשלום הבא. " +
            "הרשאת קבע אוטומטית: השאירו ריק (רץ עד ביטול)."
          }
        >
          <input
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            className={inputClass}
          />
        </Field>

        {create.error && (
          <ErrorBox message={humanizeSubscriptionError(create.error)} />
        )}

        <Actions
          onCancel={onClose}
          submitLabel="רשום מנוי"
          submitting={create.isPending}
        />
      </form>
    </Modal>
  )
}

/* ── Shared primitives used by all subscription dialogs ────────── */

export const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="my-8 w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{title}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({
  label,
  helper,
  children,
}: {
  label: string
  helper?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
      {helper && <p className="mt-1 text-xs text-gray-400">{helper}</p>}
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
      {message}
    </div>
  )
}

export function Actions({
  onCancel,
  submitLabel,
  submitting,
  destructive,
}: {
  onCancel: () => void
  submitLabel: string
  submitting?: boolean
  destructive?: boolean
}) {
  const submitClasses = destructive
    ? "bg-red-600 hover:bg-red-700"
    : "bg-blue-600 hover:bg-blue-700"
  return (
    <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
      <button
        type="button"
        onClick={onCancel}
        className="rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
      >
        ביטול
      </button>
      <button
        type="submit"
        disabled={submitting}
        className={`rounded-lg px-6 py-2.5 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${submitClasses}`}
      >
        {submitting ? "שומר..." : submitLabel}
      </button>
    </div>
  )
}
