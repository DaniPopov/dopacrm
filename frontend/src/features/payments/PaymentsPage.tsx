import { useMemo, useState } from "react"
import { PageHeader } from "@/components/ui/page-header"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizePaymentError } from "@/lib/api-errors"
import type { PaymentMethod } from "@/lib/api-types"
import { RefundPaymentDialog } from "./RefundPaymentDialog"
import { usePayments, useRevenueSummary } from "./hooks"
import type { Payment } from "./types"

const METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: "מזומן",
  credit_card: "אשראי",
  standing_order: "הוראת קבע",
  other: "אחר",
}

/**
 * /payments — the accountant's view.
 *
 * Filterable table + revenue banner up top. Refund actions only render
 * for owner+ (the backend enforces too — this is just UI cleanliness).
 *
 * Recording new payments happens from the member detail page where the
 * "+ Record Payment" button auto-fills from the active subscription.
 * The standalone /payments page is read + refund only — no record
 * button here, otherwise we'd need a member-picker which adds friction
 * for no real benefit.
 */
export default function PaymentsPage() {
  const { user } = useAuth()
  const [methodFilter, setMethodFilter] = useState<PaymentMethod | "">("")
  const [includeRefunds, setIncludeRefunds] = useState(true)
  const [pendingRefund, setPendingRefund] = useState<Payment | null>(null)

  const canRefund = user?.role === "owner" || user?.role === "super_admin"

  const { data: payments, isLoading, error } = usePayments({
    method: methodFilter || undefined,
    includeRefunds,
    limit: 200,
  })
  const { data: summary } = useRevenueSummary()

  // Build a map of original-payment-id → list of refund rows so the
  // refund button can be hidden once nothing's left.
  const refundsByOriginal = useMemo(() => {
    const map = new Map<string, number>()  // original_id → cents already refunded
    for (const p of payments ?? []) {
      if (p.refund_of_payment_id) {
        const prev = map.get(p.refund_of_payment_id) ?? 0
        map.set(p.refund_of_payment_id, prev + -p.amount_cents)
      }
    }
    return map
  }, [payments])

  function isFullyRefunded(p: Payment): boolean {
    if (p.refund_of_payment_id) return false  // refund rows themselves aren't refundable
    if (p.amount_cents <= 0) return false
    const refunded = refundsByOriginal.get(p.id) ?? 0
    return refunded >= p.amount_cents
  }

  return (
    <div>
      <PageHeader title="תשלומים" subtitle="ספר ההכנסות" />

      {summary && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50/40 px-4 py-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <div className="text-xs uppercase tracking-wide text-emerald-700">
                הכנסות החודש
              </div>
              <div className="text-2xl font-bold text-emerald-900">
                {(summary.this_month.cents / 100).toLocaleString()} {summary.currency}
              </div>
            </div>
            {summary.mom_pct !== null && (
              <div className="text-sm">
                <span
                  className={
                    summary.mom_pct >= 0 ? "text-emerald-700" : "text-red-700"
                  }
                >
                  {summary.mom_pct >= 0 ? "▲" : "▼"} {Math.abs(summary.mom_pct)}%
                </span>
                <span className="ml-2 text-gray-600">
                  לעומת חודש קודם ({(summary.last_month.cents / 100).toLocaleString()}{" "}
                  {summary.currency})
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <select
          value={methodFilter}
          onChange={(e) => setMethodFilter(e.target.value as PaymentMethod | "")}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        >
          <option value="">כל אמצעי התשלום</option>
          <option value="cash">מזומן</option>
          <option value="credit_card">אשראי</option>
          <option value="standing_order">הוראת קבע</option>
          <option value="other">אחר</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={includeRefunds}
            onChange={(e) => setIncludeRefunds(e.target.checked)}
            className="rounded border-gray-300"
          />
          הצג גם החזרים
        </label>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {humanizePaymentError(error)}
        </div>
      ) : !payments || payments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 p-12 text-center text-sm text-gray-400">
          אין תשלומים עדיין. רישומים נוספים מבוצעים מתוך עמוד המנוי.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50/50 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">תאריך</th>
                <th className="px-4 py-2">סכום</th>
                <th className="px-4 py-2">שיטה</th>
                <th className="px-4 py-2">הערות</th>
                <th className="px-4 py-2">פעולות</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payments.map((p) => {
                const refund = p.refund_of_payment_id !== null
                const fullyRefunded = isFullyRefunded(p)
                return (
                  <tr key={p.id} className={refund ? "bg-red-50/30" : ""}>
                    <td className="px-4 py-3 text-gray-700" dir="ltr">
                      {p.paid_at}
                    </td>
                    <td
                      className={`px-4 py-3 font-medium ${
                        refund ? "text-red-700" : "text-gray-900"
                      }`}
                    >
                      {refund && "🔻 "}
                      {(p.amount_cents / 100).toLocaleString()} {p.currency}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {METHOD_LABELS[p.payment_method]}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {p.notes ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {canRefund && !refund && !fullyRefunded && (
                        <button
                          onClick={() => setPendingRefund(p)}
                          className="text-xs font-semibold text-red-600 hover:underline"
                        >
                          החזר
                        </button>
                      )}
                      {fullyRefunded && (
                        <span className="text-xs text-gray-400">הוחזר במלואו</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {pendingRefund && (
        <RefundPaymentDialog
          payment={pendingRefund}
          currency={pendingRefund.currency}
          onSuccess={() => setPendingRefund(null)}
          onCancel={() => setPendingRefund(null)}
        />
      )}
    </div>
  )
}
