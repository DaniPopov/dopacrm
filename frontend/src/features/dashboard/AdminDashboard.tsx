import StatCard from "./StatCard"

/**
 * super_admin dashboard — platform-level metrics.
 * Widgets are placeholders until the backend endpoints land.
 */
export default function AdminDashboard() {
  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">דשבורד ניהול פלטפורמה</h1>
        <p className="mt-1 text-sm text-gray-500">
          מבט על על כל חדרי הכושר במערכת
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon="🏢" label="סה״כ חדרי כושר" value="--" hint="בקרוב" />
        <StatCard icon="✅" label="חדרי כושר פעילים" value="--" hint="בקרוב" />
        <StatCard icon="🆕" label="חדרי כושר חדשים החודש" value="--" hint="בקרוב" />
        <StatCard icon="👥" label="סה״כ משתמשים" value="--" hint="בקרוב" />
      </div>
    </>
  )
}
