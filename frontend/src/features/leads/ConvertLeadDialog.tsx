import { useState } from "react"
import { usePlans } from "@/features/plans/hooks"
import { humanizeLeadError } from "@/lib/api-errors"
import { useConvertLead } from "./hooks"
import type { Lead } from "./types"

const PAYMENT_METHODS = [
  { value: "cash", label: "מזומן" },
  { value: "credit_card", label: "אשראי" },
  { value: "standing_order", label: "הוראת קבע" },
  { value: "other", label: "אחר" },
] as const

type PaymentMethod = (typeof PAYMENT_METHODS)[number]["value"]

interface Props {
  lead: Lead
  onSuccess: (memberId: string) => void
  onCancel: () => void
}

/**
 * Convert a lead → Member + first Subscription in one transaction.
 *
 * Auto-fills name/phone/email from the lead. User picks: plan, start
 * date (default today), payment method. Optionally copies the lead's
 * notes to the new member.
 *
 * On 409 phone collision (a member with this phone already exists), we
 * surface the Hebrew message inline rather than closing the dialog —
 * the operator probably wants to look up the existing member.
 */
export function ConvertLeadDialog({ lead, onSuccess, onCancel }: Props) {
  const today = new Date().toISOString().split("T")[0]
  const [planId, setPlanId] = useState<string>("")
  const [startDate, setStartDate] = useState<string>(today)
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash")
  const [copyNotes, setCopyNotes] = useState(true)

  const { data: plans, isLoading: plansLoading } = usePlans()
  const convert = useConvertLead()

  const activePlans = (plans ?? []).filter((p) => p.is_active)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!planId) return
    convert.mutate(
      {
        id: lead.id,
        data: {
          plan_id: planId,
          payment_method: paymentMethod,
          start_date: startDate,
          copy_notes_to_member: copyNotes,
        },
      },
      {
        onSuccess: (result) => onSuccess(result.member.id),
      },
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-bold text-gray-900">המרת ליד למנוי</h2>
        <p className="mb-5 text-sm text-gray-500">
          ייווצרו מנוי + מנוי-תוכנית בפעולה אחת.
        </p>

        {/* Auto-filled preview */}
        <div className="mb-5 rounded-lg border border-gray-100 bg-gray-50/50 p-3 text-sm">
          <div className="mb-1 text-xs font-medium text-gray-500">פרטי הליד</div>
          <div className="text-gray-900">
            {lead.first_name} {lead.last_name} · <span dir="ltr">{lead.phone}</span>
          </div>
          {lead.email && (
            <div className="text-gray-500" dir="ltr">
              {lead.email}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              מסלול <span className="text-red-500">*</span>
            </label>
            <select
              value={planId}
              onChange={(e) => setPlanId(e.target.value)}
              required
              disabled={plansLoading}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
            >
              <option value="">— בחרו מסלול —</option>
              {activePlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {(p.price_cents / 100).toFixed(0)} {p.currency}
                </option>
              ))}
            </select>
            {!plansLoading && activePlans.length === 0 && (
              <p className="mt-1 text-xs text-amber-700">
                אין מסלולים פעילים. צרו מסלול לפני המרה.
              </p>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                תאריך התחלה
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                אמצעי תשלום
              </label>
              <select
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              >
                {PAYMENT_METHODS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={copyNotes}
              onChange={(e) => setCopyNotes(e.target.checked)}
              className="rounded border-gray-300"
            />
            העתק הערות מהליד למנוי
          </label>

          {convert.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {humanizeLeadError(convert.error)}
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
              disabled={convert.isPending || !planId}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {convert.isPending ? "ממיר..." : "המר למנוי"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
