import { useState, type FormEvent } from "react"
import { usePlans } from "@/features/plans/hooks"
import { humanizeSubscriptionError } from "@/lib/api-errors"
import { useChangePlan } from "./hooks"
import {
  Actions,
  ErrorBox,
  Field,
  inputClass,
  Modal,
} from "./SubscriptionEnrollDialog"

/**
 * Switch the member to a different plan.
 *
 * Old sub becomes ``replaced`` (NOT ``cancelled`` — critical for reports),
 * new sub starts with a fresh price snapshot from the new plan. Atomic.
 *
 * UI: plan picker filtered to active plans, excluding the current plan
 * (prevents the same-plan 409 before submit). Optional effective date —
 * default today, future dates allowed for "switch me at the start of
 * next month" without us having to build scheduled-switch infrastructure.
 */
export default function SubscriptionChangePlanDialog({
  subscriptionId,
  currentPlanId,
  onClose,
  onSuccess,
}: {
  subscriptionId: string
  currentPlanId: string
  onClose: () => void
  onSuccess?: () => void
}) {
  const { data: plans, isLoading: plansLoading } = usePlans()
  const change = useChangePlan()

  const [newPlanId, setNewPlanId] = useState("")
  const [effectiveDate, setEffectiveDate] = useState("")

  // Hide the current plan from the picker so staff can't accidentally pick it.
  const candidatePlans = (plans ?? []).filter((p) => p.id !== currentPlanId)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!newPlanId) return
    change.mutate(
      {
        id: subscriptionId,
        data: {
          new_plan_id: newPlanId,
          effective_date: effectiveDate || null,
        },
      },
      {
        onSuccess: () => {
          change.reset()
          onSuccess?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal onClose={onClose} title="החלפת מסלול">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-600">
          המסלול הנוכחי יסומן כ"הוחלף" (לא כמבוטל — הבדל חשוב בדוחות).
          המסלול החדש יתחיל עם המחיר הנוכחי שלו.
        </p>

        <Field label="מסלול חדש *">
          {plansLoading ? (
            <div className="text-sm text-gray-400">טוען מסלולים...</div>
          ) : candidatePlans.length === 0 ? (
            <div className="text-sm text-gray-500">אין מסלולים אחרים זמינים</div>
          ) : (
            <select
              required
              value={newPlanId}
              onChange={(e) => setNewPlanId(e.target.value)}
              className={inputClass}
            >
              <option value="">בחרו מסלול</option>
              {candidatePlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {(p.price_cents / 100).toLocaleString("he-IL")} ₪
                </option>
              ))}
            </select>
          )}
        </Field>

        <Field label="תאריך המעבר" helper="השאירו ריק לתאריך היום. תאריך עתידי נשמר כתאריך התחלה של המנוי החדש.">
          <input
            type="date"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            className={inputClass}
          />
        </Field>

        {change.error && <ErrorBox message={humanizeSubscriptionError(change.error)} />}

        <Actions
          onCancel={onClose}
          submitLabel="החלף מסלול"
          submitting={change.isPending}
        />
      </form>
    </Modal>
  )
}
