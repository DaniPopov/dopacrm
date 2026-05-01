import { useEffect, useState } from "react"
import { humanizePaymentError } from "@/lib/api-errors"
import type { PaymentMethod } from "@/lib/api-types"
import { useRecordPayment } from "./hooks"

const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "מזומן" },
  { value: "credit_card", label: "אשראי" },
  { value: "standing_order", label: "הוראת קבע" },
  { value: "other", label: "אחר" },
]

interface ActiveSubContext {
  /** Subscription id to pre-link the payment against. Null = drop-in. */
  subscriptionId: string | null
  /** Plan price (in cents) used to auto-fill the amount. */
  defaultAmountCents: number
  /** Default payment method (typically the sub's recorded method). */
  defaultMethod: PaymentMethod
}

interface Props {
  memberId: string
  /** When set, dialog auto-fills amount + method from the active sub
   * and locks the subscription_id link. Pass null for the standalone
   * /payments page (no sub context). */
  activeSub?: ActiveSubContext | null
  onSuccess: () => void
  onCancel: () => void
}

/**
 * RecordPaymentDialog — the "+ Record Payment" form.
 *
 * Auto-fills from the member's active subscription when one's passed in
 * (the common case from the member detail page). For the standalone
 * /payments page, the user fills everything manually.
 *
 * The "Backdate" toggle exposes a date picker that allows >30 days back
 * — small friction against typos. ``paid_at`` defaults to today;
 * future dates are rejected at the backend.
 */
export function RecordPaymentDialog({
  memberId,
  activeSub,
  onSuccess,
  onCancel,
}: Props) {
  const today = new Date().toISOString().split("T")[0]

  const [amount, setAmount] = useState<string>(
    activeSub ? String(activeSub.defaultAmountCents / 100) : "",
  )
  const [method, setMethod] = useState<PaymentMethod>(
    activeSub?.defaultMethod ?? "cash",
  )
  const [paidAt, setPaidAt] = useState<string>(today)
  const [showBackdate, setShowBackdate] = useState(false)
  const [linkSub, setLinkSub] = useState<boolean>(activeSub !== null && activeSub !== undefined)
  const [notes, setNotes] = useState("")

  const record = useRecordPayment()

  // If the active-sub context changes, refresh defaults.
  useEffect(() => {
    if (activeSub) {
      setAmount(String(activeSub.defaultAmountCents / 100))
      setMethod(activeSub.defaultMethod)
      setLinkSub(true)
    }
  }, [activeSub])

  const isBackdated = (() => {
    const today_ms = new Date(today).getTime()
    const paid_ms = new Date(paidAt).getTime()
    const days = Math.round((today_ms - paid_ms) / (1000 * 60 * 60 * 24))
    return days > 30
  })()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(amount) * 100)
    if (!Number.isFinite(cents) || cents <= 0) return
    record.mutate(
      {
        member_id: memberId,
        amount_cents: cents,
        payment_method: method,
        paid_at: paidAt,
        subscription_id: linkSub && activeSub ? activeSub.subscriptionId : null,
        notes: notes.trim() || null,
        backdate: isBackdated,
      },
      { onSuccess },
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-bold text-gray-900">רישום תשלום</h2>
        <p className="mb-5 text-sm text-gray-500">
          הכנסת תשלום שנגבה מהמנוי. תאריך התשלום יכול להיות אתמול / לפני ימים.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              סכום (₪) <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                אמצעי תשלום
              </label>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as PaymentMethod)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              >
                {PAYMENT_METHODS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                תאריך התשלום
              </label>
              <input
                type="date"
                value={paidAt}
                onChange={(e) => setPaidAt(e.target.value)}
                max={today}
                min={
                  showBackdate ? undefined : new Date(Date.now() - 30 * 86400_000)
                    .toISOString()
                    .split("T")[0]
                }
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={showBackdate}
              onChange={(e) => setShowBackdate(e.target.checked)}
              className="rounded border-gray-300"
            />
            אפשר תאריך מעבר ל-30 יום אחורה
          </label>

          {activeSub && (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={linkSub}
                onChange={(e) => setLinkSub(e.target.checked)}
                className="rounded border-gray-300"
              />
              קשר למנוי הפעיל (אחרת — יוגדר כתשלום חד-פעמי)
            </label>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              הערות
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="למשל: דמי הרשמה, drop-in yoga"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          {record.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {humanizePaymentError(record.error)}
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
              disabled={record.isPending || !amount || Number(amount) <= 0}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {record.isPending ? "שומר..." : "רשום תשלום"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
