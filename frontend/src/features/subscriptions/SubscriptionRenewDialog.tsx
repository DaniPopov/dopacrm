import { useState, type FormEvent } from "react"
import { humanizeSubscriptionError } from "@/lib/api-errors"
import { useRenewSubscription } from "./hooks"
import {
  Actions,
  ErrorBox,
  Field,
  inputClass,
  Modal,
} from "./SubscriptionEnrollDialog"

/**
 * Renew a subscription (extend expires_at).
 *
 * Default (no date chosen) = push expires_at forward by the plan's billing
 * period. Override by entering an explicit date — common for
 * "she paid for 2 months upfront" scenarios.
 *
 * Works on `active` subs (extending before they expire) and on `expired`
 * subs (rescuing a lapsed member on the same row — tenure + price stay put).
 */
export default function SubscriptionRenewDialog({
  subscriptionId,
  currentExpiresAt,
  onClose,
  onSuccess,
}: {
  subscriptionId: string
  /** Shown as helper text so staff can see what they're extending. */
  currentExpiresAt: string | null
  onClose: () => void
  onSuccess?: () => void
}) {
  const renew = useRenewSubscription()
  const [newExpiresAt, setNewExpiresAt] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    renew.mutate(
      {
        id: subscriptionId,
        data: { new_expires_at: newExpiresAt || null },
      },
      {
        onSuccess: () => {
          renew.reset()
          onSuccess?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal onClose={onClose} title="חידוש מנוי">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-600">
          {currentExpiresAt
            ? `תוקף נוכחי: ${currentExpiresAt}`
            : "מנוי בהרשאת קבע אוטומטית (ללא תאריך תפוגה)"}
        </p>

        <Field
          label="תוקף חדש (אופציונלי)"
          helper="אם תשאירו ריק — התוקף יוארך בתקופה אחת לפי המסלול (חודש / רבעון / שנה)."
        >
          <input
            type="date"
            value={newExpiresAt}
            onChange={(e) => setNewExpiresAt(e.target.value)}
            className={inputClass}
          />
        </Field>

        {renew.error && <ErrorBox message={humanizeSubscriptionError(renew.error)} />}

        <Actions onCancel={onClose} submitLabel="חדש" submitting={renew.isPending} />
      </form>
    </Modal>
  )
}
