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
import { PAYMENT_METHOD_OPTIONS } from "./paymentMethods"
import type { PaymentMethod } from "./types"

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
  currentPaymentMethod,
  onClose,
  onSuccess,
}: {
  subscriptionId: string
  /** Shown as helper text so staff can see what they're extending. */
  currentExpiresAt: string | null
  /** Current payment method, shown + prefilled in the optional override dropdown. */
  currentPaymentMethod: PaymentMethod
  onClose: () => void
  onSuccess?: () => void
}) {
  const renew = useRenewSubscription()
  const [newExpiresAt, setNewExpiresAt] = useState("")
  // "" sentinel = "don't change method". Actual enum values trigger an update.
  const [newPaymentMethod, setNewPaymentMethod] = useState<"" | PaymentMethod>("")
  const [newPaymentDetail, setNewPaymentDetail] = useState("")

  const methodChanged =
    newPaymentMethod !== "" && newPaymentMethod !== currentPaymentMethod

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    renew.mutate(
      {
        id: subscriptionId,
        data: {
          new_expires_at: newExpiresAt || null,
          new_payment_method: methodChanged ? newPaymentMethod : null,
          new_payment_method_detail: methodChanged ? newPaymentDetail.trim() || null : null,
        },
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

        <Field
          label="החלפת אמצעי תשלום (אופציונלי)"
          helper="למשל: מעבר מתשלום במזומן להוראת קבע. השאירו ריק כדי לא לשנות."
        >
          <select
            value={newPaymentMethod}
            onChange={(e) =>
              setNewPaymentMethod(e.target.value as "" | PaymentMethod)
            }
            className={inputClass}
          >
            <option value="">ללא שינוי</option>
            {PAYMENT_METHOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        {methodChanged && (
          <Field
            label="פרטים (אופציונלי)"
            helper={
              newPaymentMethod === "other"
                ? "מומלץ לציין תיאור חופשי"
                : "אופציונלי — למשל מספר כרטיס/אסמכתה"
            }
          >
            <input
              type="text"
              maxLength={200}
              value={newPaymentDetail}
              onChange={(e) => setNewPaymentDetail(e.target.value)}
              className={inputClass}
            />
          </Field>
        )}

        {renew.error && <ErrorBox message={humanizeSubscriptionError(renew.error)} />}

        <Actions onCancel={onClose} submitLabel="חדש" submitting={renew.isPending} />
      </form>
    </Modal>
  )
}
