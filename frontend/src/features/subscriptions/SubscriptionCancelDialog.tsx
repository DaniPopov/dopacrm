import { useState, type FormEvent } from "react"
import { humanizeSubscriptionError } from "@/lib/api-errors"
import { useCancelSubscription } from "./hooks"
import {
  Actions,
  ErrorBox,
  Field,
  inputClass,
  Modal,
} from "./SubscriptionEnrollDialog"

/**
 * Cancel a subscription (hard-terminal).
 *
 * Common-reason dropdown + optional free-text detail. The reason keys
 * are canonical so the owner's churn-analytics dashboard can bucket them
 * deterministically; "other" lets staff capture the unusual cases.
 *
 * Cancel is red / destructive — this is the "member actively left"
 * terminal state. Undo = new sub; the old one stays as history.
 */

const REASON_OPTIONS: { value: string; label: string }[] = [
  { value: "moved_away", label: "עבר דירה" },
  { value: "too_expensive", label: "יקר מדי" },
  { value: "not_using", label: "לא מנצל" },
  { value: "injury", label: "פציעה" },
  { value: "other", label: "אחר" },
]

export default function SubscriptionCancelDialog({
  subscriptionId,
  onClose,
  onSuccess,
}: {
  subscriptionId: string
  onClose: () => void
  onSuccess?: () => void
}) {
  const cancel = useCancelSubscription()
  const [reason, setReason] = useState("")
  const [detail, setDetail] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    cancel.mutate(
      {
        id: subscriptionId,
        data: {
          reason: reason || null,
          detail: detail || null,
        },
      },
      {
        onSuccess: () => {
          cancel.reset()
          onSuccess?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal onClose={onClose} title="ביטול מנוי">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-red-700">
          פעולה זו סופית. המנוי לא יוחזר. אם תרצו לחדש את החברות בעתיד,
          תצטרכו ליצור מנוי חדש.
        </p>

        <Field label="סיבה (אופציונלי)">
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={inputClass}
          >
            <option value="">ללא סיבה</option>
            {REASON_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="הערות (אופציונלי)">
          <textarea
            rows={2}
            maxLength={500}
            value={detail}
            onChange={(e) => setDetail(e.target.value)}
            placeholder="למשל: מתחייב להחזיר את המפתח"
            className={`${inputClass} resize-y`}
          />
        </Field>

        {cancel.error && <ErrorBox message={humanizeSubscriptionError(cancel.error)} />}

        <Actions
          onCancel={onClose}
          submitLabel="בטל מנוי"
          submitting={cancel.isPending}
          destructive
        />
      </form>
    </Modal>
  )
}
