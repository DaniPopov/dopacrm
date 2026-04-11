import { useAuth } from "@/features/auth/auth-provider"
import StatCard from "./StatCard"

/**
 * Gym owner / staff / sales dashboard — tenant-scoped metrics.
 * Widgets are placeholders until the members/payments/leads features land.
 */
export default function GymDashboard() {
  const { user } = useAuth()
  const displayName = user?.email?.split("@")[0] ?? ""

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
        <StatCard icon="💰" label="הכנסות החודש" value="--" hint="בקרוב" />
        <StatCard icon="📈" label="MRR" value="--" hint="בקרוב" />
        <StatCard icon="🎯" label="לידים בצינור" value="--" hint="בקרוב" />
      </div>

      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">פעולות מהירות</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction icon="➕" label="הוספת מנוי" />
          <QuickAction icon="💳" label="רישום תשלום" />
          <QuickAction icon="📝" label="הוספת ליד" />
        </div>
      </div>
    </>
  )
}

function QuickAction({ icon, label }: { icon: string; label: string }) {
  return (
    <button className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 text-right transition-all hover:border-blue-300 hover:bg-blue-50/30">
      <span className="text-2xl">{icon}</span>
      <span className="font-medium text-gray-900">{label}</span>
    </button>
  )
}
