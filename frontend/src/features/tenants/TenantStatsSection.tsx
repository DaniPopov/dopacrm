import { useTenantStats } from "./hooks"

/**
 * Stats cards shown at the top of the tenant detail page.
 * Falls back to "—" while loading; shows raw numbers once fetched.
 */
export default function TenantStatsSection({ tenantId }: { tenantId: string }) {
  const { data, isLoading, error } = useTenantStats(tenantId)

  const items: { icon: string; label: string; value: string; hint?: string }[] = [
    {
      icon: "👥",
      label: "מנויים פעילים",
      value: fmt(data?.active_members, isLoading, error),
      hint: data ? `מתוך ${data.total_members} סה״כ` : undefined,
    },
    {
      icon: "📋",
      label: "סה״כ מנויים",
      value: fmt(data?.total_members, isLoading, error),
    },
    {
      icon: "👤",
      label: "משתמשי מערכת",
      value: fmt(data?.total_users, isLoading, error),
      hint: "צוות של חדר הכושר",
    },
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <span className="text-lg">{item.icon}</span>
            <span className="text-sm text-gray-500">{item.label}</span>
          </div>
          <div className="mt-2 text-3xl font-bold text-gray-900">{item.value}</div>
          {item.hint && <p className="mt-0.5 text-xs text-gray-400">{item.hint}</p>}
        </div>
      ))}
    </div>
  )
}

function fmt(value: number | undefined, isLoading: boolean, error: unknown): string {
  if (isLoading) return "…"
  if (error) return "—"
  return String(value ?? 0)
}
