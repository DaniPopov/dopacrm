import { useState, type FormEvent } from "react"
import { humanizeSubscriptionError } from "@/lib/api-errors"
import { useFreezeSubscription } from "./hooks"
import {
  Actions,
  ErrorBox,
  Field,
  inputClass,
  Modal,
} from "./SubscriptionEnrollDialog"

/**
 * Freeze a subscription.
 *
 * Optional ``frozen_until`` date — if set, the nightly beat job auto-unfreezes
 * on or after that date and extends ``expires_at`` by the frozen duration.
 * Omit for an open-ended freeze (manual unfreeze only).
 */
export default function SubscriptionFreezeDialog({
  subscriptionId,
  onClose,
  onSuccess,
}: {
  subscriptionId: string
  onClose: () => void
  onSuccess?: () => void
}) {
  const freeze = useFreezeSubscription()
  const [frozenUntil, setFrozenUntil] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    freeze.mutate(
      { id: subscriptionId, data: { frozen_until: frozenUntil || null } },
      {
        onSuccess: () => {
          freeze.reset()
          onSuccess?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal onClose={onClose} title="הקפאת מנוי">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-600">
          ההקפאה עוצרת את הספירה של ימי המנוי. כשתבוטל, תוקף המנוי
          יוארך בהתאם לימים שהיה מוקפא.
        </p>

        <Field
          label="הפשרה אוטומטית (אופציונלי)"
          helper="אם תבחרו תאריך, המנוי יופשר אוטומטית באותו היום. השאירו ריק להפשרה ידנית בלבד."
        >
          <input
            type="date"
            value={frozenUntil}
            onChange={(e) => setFrozenUntil(e.target.value)}
            className={inputClass}
          />
        </Field>

        {freeze.error && <ErrorBox message={humanizeSubscriptionError(freeze.error)} />}

        <Actions onCancel={onClose} submitLabel="הקפא" submitting={freeze.isPending} />
      </form>
    </Modal>
  )
}
