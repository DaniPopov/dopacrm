import StatCard from "./StatCard"
import { usePlatformStats } from "./hooks"

/**
 * super_admin dashboard — platform-level metrics.
 *
 * Pulls counts from `GET /api/v1/admin/stats`. Shows "—" while
 * loading or on error; Hebrew hints explain what the number means
 * (e.g. "כולל תקופת ניסיון" — includes trial).
 */
export default function AdminDashboard() {
  const { data, isLoading, error } = usePlatformStats()

  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">דשבורד ניהול פלטפורמה</h1>
        <p className="mt-1 text-sm text-gray-500">מבט על על כל חדרי הכושר במערכת</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon="🏢"
          label="סה״כ חדרי כושר"
          value={fmt(data?.total_tenants, isLoading, error)}
        />
        <StatCard
          icon="✅"
          label="חדרי כושר פעילים"
          value={fmt(data?.active_tenants, isLoading, error)}
          hint="כולל תקופת ניסיון"
        />
        <StatCard
          icon="🆕"
          label="חדרי כושר חדשים החודש"
          value={fmt(data?.new_tenants_this_month, isLoading, error)}
        />
        <StatCard
          icon="👥"
          label="סה״כ משתמשים"
          value={fmt(data?.total_users, isLoading, error)}
          hint={data ? `${data.total_members} מנויים במערכת` : undefined}
        />
      </div>
    </>
  )
}

/** "…" while loading, "—" on error, the number otherwise. */
function fmt(value: number | undefined, isLoading: boolean, error: unknown): string {
  if (isLoading) return "…"
  if (error) return "—"
  return String(value ?? 0)
}
