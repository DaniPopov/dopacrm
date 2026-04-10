import { useState } from "react"
import { useTenants, useCreateTenant, useSuspendTenant } from "./hooks"
import type { Tenant, CreateTenantRequest } from "./types"

export default function TenantListPage() {
  const { data: tenants, isLoading, error } = useTenants()
  const [showCreate, setShowCreate] = useState(false)

  return (
    <div>
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">חדרי כושר</h1>
          <p className="mt-1 text-sm text-gray-500">ניהול כל חדרי הכושר בפלטפורמה</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700"
        >
          + הוספת חדר כושר
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateTenantForm onClose={() => setShowCreate(false)} />
      )}

      {/* Table */}
      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="py-20 text-center text-red-500">{error.message}</div>
      ) : tenants?.length === 0 ? (
        <div className="py-20 text-center text-gray-400">
          אין חדרי כושר עדיין. הוסיפו את הראשון!
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="px-5 py-3 font-medium text-gray-500">שם</th>
                <th className="px-5 py-3 font-medium text-gray-500">Slug</th>
                <th className="px-5 py-3 font-medium text-gray-500">סטטוס</th>
                <th className="px-5 py-3 font-medium text-gray-500">טלפון</th>
                <th className="px-5 py-3 font-medium text-gray-500">אזור זמן</th>
                <th className="px-5 py-3 font-medium text-gray-500">מטבע</th>
                <th className="px-5 py-3 font-medium text-gray-500">תאריך הצטרפות</th>
                <th className="px-5 py-3 font-medium text-gray-500">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {tenants?.map((tenant) => (
                <TenantRow key={tenant.id} tenant={tenant} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ── Status badge ─────────────────────────────────────────────── */

const statusConfig = {
  active: { label: "פעיל", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  trial: { label: "ניסיון", className: "bg-blue-50 text-blue-700 border-blue-200" },
  suspended: { label: "מושהה", className: "bg-red-50 text-red-700 border-red-200" },
  cancelled: { label: "מבוטל", className: "bg-gray-50 text-gray-500 border-gray-200" },
}

function StatusBadge({ status }: { status: Tenant["status"] }) {
  const config = statusConfig[status]
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  )
}

/* ── Table row ────────────────────────────────────────────────── */

function TenantRow({ tenant }: { tenant: Tenant }) {
  const suspend = useSuspendTenant()
  const canSuspend = tenant.status === "active" || tenant.status === "trial"

  return (
    <tr className="border-b border-gray-50 transition-colors hover:bg-gray-50/50">
      <td className="px-5 py-3.5 font-medium text-gray-900">{tenant.name}</td>
      <td className="px-5 py-3.5 font-mono text-xs text-gray-500">{tenant.slug}</td>
      <td className="px-5 py-3.5"><StatusBadge status={tenant.status} /></td>
      <td className="px-5 py-3.5 text-gray-600" dir="ltr">{tenant.phone || "—"}</td>
      <td className="px-5 py-3.5 text-gray-600" dir="ltr">{tenant.timezone}</td>
      <td className="px-5 py-3.5 text-gray-600">{tenant.currency}</td>
      <td className="px-5 py-3.5 text-gray-500" dir="ltr">
        {new Date(tenant.created_at).toLocaleDateString("he-IL")}
      </td>
      <td className="px-5 py-3.5">
        {canSuspend ? (
          <button
            onClick={() => suspend.mutate(tenant.id)}
            disabled={suspend.isPending}
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-100 disabled:opacity-50"
          >
            {suspend.isPending ? "..." : "השהה"}
          </button>
        ) : (
          <span className="text-xs text-gray-400">—</span>
        )}
      </td>
    </tr>
  )
}

/* ── Create form ──────────────────────────────────────────────── */

function CreateTenantForm({ onClose }: { onClose: () => void }) {
  const create = useCreateTenant()
  const [form, setForm] = useState<CreateTenantRequest>({
    slug: "",
    name: "",
    phone: "",
    timezone: "Asia/Jerusalem",
    currency: "ILS",
    locale: "he-IL",
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    create.mutate(form, {
      onSuccess: () => onClose(),
    })
  }

  return (
    <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-bold text-gray-900">חדר כושר חדש</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
      </div>
      <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">שם</label>
          <input
            type="text"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="IronFit Tel Aviv"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Slug (URL)</label>
          <input
            type="text"
            required
            value={form.slug}
            onChange={(e) => setForm({ ...form, slug: e.target.value })}
            placeholder="ironfit-tlv"
            dir="ltr"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">טלפון</label>
          <input
            type="text"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            placeholder="+972-3-555-1234"
            dir="ltr"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">מטבע</label>
          <select
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value })}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          >
            <option value="ILS">ILS — שקל</option>
            <option value="USD">USD — דולר</option>
            <option value="EUR">EUR — יורו</option>
          </select>
        </div>

        {create.error && (
          <div className="sm:col-span-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {create.error.message}
          </div>
        )}

        <div className="sm:col-span-2 flex gap-3 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            ביטול
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {create.isPending ? "יוצר..." : "צור חדר כושר"}
          </button>
        </div>
      </form>
    </div>
  )
}
