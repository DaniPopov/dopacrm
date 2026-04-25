/**
 * TenantFeaturesSection — super_admin's per-tenant feature toggle UI.
 *
 * Lives on /tenants/{id}. One checkbox per gated feature. Owner /
 * staff don't see this section (caller component gates visibility on
 * user.role).
 *
 * Toggling a flag immediately PATCHes /tenants/{id}/features and
 * updates the cached tenant. The owner of that tenant will see the
 * sidebar gain/lose the entry on their next /auth/me refresh.
 */

import { useEffect, useState } from "react"
import { humanizeScheduleError } from "@/lib/api-errors"
import { useUpdateTenantFeatures } from "./hooks"

const GATED_FEATURES = [
  { key: "coaches", label: "מאמנים + חישוב שכר" },
  { key: "schedule", label: "לוח שיעורים שבועי" },
] as const

interface Props {
  tenantId: string
  features: Record<string, boolean>
}

export function TenantFeaturesSection({ tenantId, features }: Props) {
  const mutation = useUpdateTenantFeatures()
  const [pending, setPending] = useState<Record<string, boolean>>({})

  // Reset pending state when the cached features change (e.g. after save).
  useEffect(() => {
    setPending({})
  }, [features])

  const dirty = Object.keys(pending).length > 0
  const effective = { ...features, ...pending }

  function toggle(key: string) {
    setPending((p) => ({ ...p, [key]: !effective[key] }))
  }

  function handleSave() {
    if (!dirty) return
    mutation.mutate({ tenantId, data: pending })
  }

  return (
    <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">תכונות</h2>
          <p className="text-sm text-gray-500">
            הפעלה והשבתה של תכונות מתקדמות עבור חדר כושר זה.
          </p>
        </div>
        {dirty && (
          <button
            onClick={handleSave}
            disabled={mutation.isPending}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {mutation.isPending ? "שומר..." : "שמור שינויים"}
          </button>
        )}
      </div>

      <ul className="space-y-2">
        {GATED_FEATURES.map((f) => (
          <li
            key={f.key}
            className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3"
          >
            <div>
              <div className="font-medium text-gray-900">{f.label}</div>
              <div className="text-xs text-gray-400" dir="ltr">
                {f.key}
              </div>
            </div>
            <label className="inline-flex cursor-pointer items-center">
              <input
                type="checkbox"
                checked={!!effective[f.key]}
                onChange={() => toggle(f.key)}
                className="h-4 w-4 cursor-pointer accent-blue-600"
              />
            </label>
          </li>
        ))}
      </ul>

      {mutation.error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {humanizeScheduleError(mutation.error)}
        </div>
      )}
    </section>
  )
}
