import { useState } from "react"
import { useAuth } from "@/features/auth/auth-provider"
import { useCurrentSubscriptionForMember } from "@/features/subscriptions/hooks"
import { humanizePaymentError } from "@/lib/api-errors"
import type { PaymentMethod } from "@/lib/api-types"
import { RecordPaymentDialog } from "./RecordPaymentDialog"
import { RefundPaymentDialog } from "./RefundPaymentDialog"
import { useMemberPayments } from "./hooks"
import type { Payment } from "./types"

const METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: "מזומן",
  credit_card: "אשראי",
  standing_order: "הוראת קבע",
  other: "אחר",
}

interface Props {
  memberId: string
}

/**
 * Payments section embedded on the member detail page (under the
 * subscription block). Lists the member's payment history + the
 * prominent "+ Record Payment" button that drives the walk-in flow.
 *
 * Auto-fills from the member's live subscription so the common case
 * (member walks in, pays the monthly fee, staff hits two buttons)
 * stays fast.
 */
export function PaymentsSection({ memberId }: Props) {
  const { user } = useAuth()
  const [showRecord, setShowRecord] = useState(false)
  const [pendingRefund, setPendingRefund] = useState<Payment | null>(null)

  const canWrite =
    user?.role === "owner" ||
    user?.role === "sales" ||
    user?.role === "staff" ||
    user?.role === "super_admin"
  const canRefund = user?.role === "owner" || user?.role === "super_admin"

  const { data: payments, isLoading, error } = useMemberPayments(memberId)
  const { data: liveSub } = useCurrentSubscriptionForMember(memberId)

  const totals = (payments ?? []).reduce(
    (acc, p) => {
      if (p.amount_cents > 0) acc.gross += p.amount_cents
      else acc.refunds += -p.amount_cents
      return acc
    },
    { gross: 0, refunds: 0 },
  )
  const net = totals.gross - totals.refunds
  const currency = payments?.[0]?.currency ?? liveSub?.currency ?? "ILS"

  // Map original-payment → cumulative refunded so we can hide the
  // refund button once nothing's left.
  const refundedByOriginal = new Map<string, number>()
  for (const p of payments ?? []) {
    if (p.refund_of_payment_id) {
      const prev = refundedByOriginal.get(p.refund_of_payment_id) ?? 0
      refundedByOriginal.set(p.refund_of_payment_id, prev + -p.amount_cents)
    }
  }

  function isFullyRefunded(p: Payment): boolean {
    if (p.refund_of_payment_id || p.amount_cents <= 0) return false
    const refunded = refundedByOriginal.get(p.id) ?? 0
    return refunded >= p.amount_cents
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900">תשלומים</h2>
        {canWrite && (
          <button
            onClick={() => setShowRecord(true)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
          >
            + רישום תשלום
          </button>
        )}
      </div>

      {payments && payments.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-6 rounded-lg border border-gray-100 bg-gray-50/40 px-4 py-3 text-sm">
          <div>
            <span className="text-gray-500">סה"כ ששולם:</span>{" "}
            <span className="font-semibold text-gray-900">
              {(totals.gross / 100).toLocaleString()} {currency}
            </span>
          </div>
          {totals.refunds > 0 && (
            <div>
              <span className="text-gray-500">החזרים:</span>{" "}
              <span className="font-semibold text-red-700">
                -{(totals.refunds / 100).toLocaleString()} {currency}
              </span>
            </div>
          )}
          <div>
            <span className="text-gray-500">נטו:</span>{" "}
            <span className="font-bold text-gray-900">
              {(net / 100).toLocaleString()} {currency}
            </span>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="py-8 text-center text-sm text-gray-400">טוען...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {humanizePaymentError(error)}
        </div>
      ) : !payments || payments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">
          אין תשלומים עדיין. לחצו "+ רישום תשלום" להוספת הראשון.
        </div>
      ) : (
        <ul className="divide-y divide-gray-100">
          {payments.map((p) => {
            const refund = p.refund_of_payment_id !== null
            const fullyRefunded = isFullyRefunded(p)
            return (
              <li
                key={p.id}
                className={`flex items-center justify-between py-3 text-sm ${
                  refund ? "bg-red-50/30 -mx-2 px-2" : ""
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-3">
                    <span
                      className={`font-medium ${
                        refund ? "text-red-700" : "text-gray-900"
                      }`}
                    >
                      {refund && "🔻 "}
                      {(p.amount_cents / 100).toLocaleString()} {p.currency}
                    </span>
                    <span className="text-xs text-gray-500">
                      {METHOD_LABELS[p.payment_method]}
                    </span>
                    <span className="text-xs text-gray-400" dir="ltr">
                      {p.paid_at}
                    </span>
                  </div>
                  {p.notes && (
                    <div className="mt-0.5 text-xs text-gray-500">{p.notes}</div>
                  )}
                </div>
                {canRefund && !refund && !fullyRefunded && (
                  <button
                    onClick={() => setPendingRefund(p)}
                    className="ml-2 rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                  >
                    החזר
                  </button>
                )}
                {fullyRefunded && (
                  <span className="ml-2 text-xs text-gray-400">הוחזר במלואו</span>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {showRecord && (
        <RecordPaymentDialog
          memberId={memberId}
          activeSub={
            liveSub
              ? {
                  subscriptionId: liveSub.id,
                  defaultAmountCents: liveSub.price_cents,
                  defaultMethod: liveSub.payment_method,
                }
              : null
          }
          onSuccess={() => setShowRecord(false)}
          onCancel={() => setShowRecord(false)}
        />
      )}

      {pendingRefund && (
        <RefundPaymentDialog
          payment={pendingRefund}
          currency={pendingRefund.currency}
          onSuccess={() => setPendingRefund(null)}
          onCancel={() => setPendingRefund(null)}
        />
      )}
    </section>
  )
}
