import { useState } from "react"
import { humanizePaymentError } from "@/lib/api-errors"
import { usePayments, useRefundPayment } from "./hooks"
import type { Payment } from "./types"

interface Props {
  payment: Payment
  /** Currency display (just for UI). */
  currency: string
  onSuccess: () => void
  onCancel: () => void
}

/**
 * RefundPaymentDialog — owner-only refund flow.
 *
 * Computes the **remaining refundable amount** by reading existing
 * refund rows (cumulative); the input defaults to that, and the
 * Submit button blocks when the user types more.
 */
export function RefundPaymentDialog({
  payment,
  currency,
  onSuccess,
  onCancel,
}: Props) {
  // Read the existing refund chain via the standard payments list
  // (filtered by member, then matched in JS by refund_of_payment_id).
  // Avoids a dedicated endpoint just for the dialog.
  const refundsQuery = usePayments({ memberId: payment.member_id, limit: 500 })
  const refunds = (refundsQuery.data ?? []).filter(
    (p) => p.refund_of_payment_id === payment.id,
  )
  const alreadyRefunded = refunds.reduce((sum, p) => sum + -p.amount_cents, 0)
  const remaining = payment.amount_cents - alreadyRefunded

  const [amount, setAmount] = useState<string>(String(remaining / 100))
  const [reason, setReason] = useState("")
  const refund = useRefundPayment()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(amount) * 100)
    if (!Number.isFinite(cents) || cents <= 0 || cents > remaining) return
    refund.mutate(
      {
        id: payment.id,
        data: {
          amount_cents: cents,
          reason: reason.trim() || null,
        },
      },
      { onSuccess },
    )
  }

  const overflow = Math.round(Number(amount) * 100) > remaining

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-bold text-gray-900">החזר תשלום</h2>
        <p className="mb-5 text-sm text-gray-500">
          נרשמת שורת החזר חדשה — התשלום המקורי נשאר בהיסטוריה.
        </p>

        <div className="mb-5 rounded-lg border border-gray-100 bg-gray-50/50 p-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">סכום מקורי</span>
            <span className="font-medium text-gray-900">
              {(payment.amount_cents / 100).toFixed(0)} {currency}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">הוחזר עד כה</span>
            <span className="font-medium text-gray-900">
              {(alreadyRefunded / 100).toFixed(0)} {currency}
            </span>
          </div>
          <div className="mt-1 flex justify-between border-t border-gray-200 pt-1">
            <span className="font-semibold text-gray-700">ניתן עוד להחזיר</span>
            <span className="font-bold text-gray-900">
              {(remaining / 100).toFixed(0)} {currency}
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              סכום ההחזר (₪) <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              min="0"
              max={remaining / 100}
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
            />
            {overflow && (
              <p className="mt-1 text-xs text-red-700">
                הסכום שהוזן גדול מהיתרה הניתנת להחזר
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              סיבה
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="למשל: ביטול שיעור, טעות בסכום"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
            />
          </div>

          {refund.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {humanizePaymentError(refund.error)}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
            >
              ביטול
            </button>
            <button
              type="submit"
              disabled={refund.isPending || overflow || !amount || Number(amount) <= 0}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
            >
              {refund.isPending ? "מחזיר..." : "בצע החזר"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
