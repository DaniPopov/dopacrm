import { useNavigate } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"
import { useRevenueSummary } from "@/features/payments/hooks"
import StatCard from "./StatCard"

/**
 * Gym owner / staff / sales dashboard — tenant-scoped metrics.
 *
 * Revenue widgets read from ``GET /api/v1/dashboard/revenue``. Members
 * + leads-pipeline counts will swap from ``בקרוב`` to real numbers
 * when those summary endpoints land — the StatCard scaffold stays.
 */
export default function GymDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const displayName = user?.email?.split("@")[0] ?? ""

  const { data: revenue } = useRevenueSummary()

  const fmt = (cents: number, currency: string) =>
    `${(cents / 100).toLocaleString()} ${currency}`

  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">
          שלום{displayName && `, ${displayName}`} 👋
        </h1>
        <p className="mt-1 text-sm text-gray-500">מה קורה בחדר הכושר שלכם היום</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon="👥" label="מנויים פעילים" value="--" hint="בקרוב" />
        <StatCard
          icon="💰"
          label="הכנסות החודש"
          value={
            revenue ? fmt(revenue.this_month.cents, revenue.currency) : "--"
          }
          hint={
            revenue && revenue.mom_pct !== null
              ? `${revenue.mom_pct >= 0 ? "▲" : "▼"} ${Math.abs(revenue.mom_pct)}% מחודש קודם`
              : "—"
          }
        />
        <StatCard
          icon="📊"
          label="הכנסה ממוצעת למנוי משלם"
          value={
            revenue && revenue.arpm_cents > 0
              ? fmt(revenue.arpm_cents, revenue.currency)
              : "--"
          }
          hint="החודש"
        />
        <StatCard icon="🎯" label="לידים בצינור" value="--" hint="בקרוב" />
      </div>

      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">פעולות מהירות</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            icon="➕"
            label="הוספת מנוי"
            onClick={() => navigate("/members")}
          />
          <QuickAction
            icon="💳"
            label="רישום תשלום"
            onClick={() => navigate("/payments")}
          />
          <QuickAction
            icon="📝"
            label="הוספת ליד"
            onClick={() => navigate("/leads")}
          />
        </div>
      </div>
    </>
  )
}

function QuickAction({
  icon,
  label,
  onClick,
}: {
  icon: string
  label: string
  onClick?: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 text-right transition-all hover:border-blue-300 hover:bg-blue-50/30"
    >
      <span className="text-2xl">{icon}</span>
      <span className="font-medium text-gray-900">{label}</span>
    </button>
  )
}
