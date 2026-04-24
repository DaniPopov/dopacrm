/**
 * EarningsCard — totals + per-link breakdown for one coach.
 *
 * Shown on the coach detail page and (future) the dashboard. The
 * "unit" column explains WHY the number is what it is: for
 * per_attendance it's the attendance count, for per_session it's
 * distinct days, for fixed it's days in the pro-rated slice.
 */

import { SectionCard } from "@/components/ui/section-card"
import type { EarningsBreakdown } from "./types"

export function EarningsCard({
  data,
  title,
}: {
  data: EarningsBreakdown
  title?: string
}) {
  return (
    <SectionCard title={title ?? "הכנסה משוערת"}>
      <div className="mb-4 text-2xl font-semibold text-gray-900" dir="ltr">
        {formatMoney(data.total_cents, data.currency)}
      </div>
      {data.effective_from && data.effective_to && (
        <div className="mb-4 text-xs text-gray-400">
          טווח חישוב: {data.effective_from} – {data.effective_to}
        </div>
      )}
      {data.by_link.length === 0 ? (
        <div className="text-sm text-gray-400">אין שיעורים מוקצים בטווח זה</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-right text-xs text-gray-500">
              <tr>
                <th className="pb-2 pe-2 font-medium">שיעור</th>
                <th className="pb-2 pe-2 font-medium">תפקיד</th>
                <th className="pb-2 pe-2 font-medium">מודל</th>
                <th className="pb-2 pe-2 font-medium">יחידות</th>
                <th className="pb-2 pe-2 font-medium">סכום</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.by_link.map((row, i) => (
                <tr key={`${row.class_id}-${row.role}-${i}`}>
                  <td className="py-2 pe-2 font-medium text-gray-900">
                    {row.class_name ?? "—"}
                  </td>
                  <td className="py-2 pe-2 text-gray-600">{row.role}</td>
                  <td className="py-2 pe-2 text-gray-600">
                    {payModelLabel(row.pay_model)}
                  </td>
                  <td className="py-2 pe-2 text-gray-600">{row.unit_count}</td>
                  <td className="py-2 pe-2 font-mono text-gray-900" dir="ltr">
                    {formatMoney(row.cents, data.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  )
}

export function payModelLabel(model: string): string {
  return (
    {
      fixed: "משכורת קבועה",
      per_session: "לפי שיעור",
      per_attendance: "לפי כניסה",
    }[model] ?? model
  )
}

export function formatMoney(cents: number, currency: string): string {
  const amount = cents / 100
  try {
    return new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency}`
  }
}
