import { useNavigate, useParams } from "react-router-dom"
import { humanizeTenantError } from "@/lib/api-errors"
import TenantForm, { type TenantFormValues } from "./TenantForm"
import TenantStatsSection from "./TenantStatsSection"
import TenantUsersSection from "./TenantUsersSection"
import { useTenant, useUpdateTenant } from "./hooks"

/**
 * Tenant detail page — `/tenants/:id`.
 *
 * Three stacked sections: stats cards → users list → edit form. A
 * super_admin uses this page to onboard / fix up / inspect a single
 * gym's state. The standalone `/users` page was removed in favor of
 * managing users here (they're always scoped to a tenant).
 */
export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: tenant, isLoading, error } = useTenant(id ?? "")
  const update = useUpdateTenant()

  function handleSubmit(values: TenantFormValues) {
    if (!id) return
    update.mutate(
      { id, data: values },
      {
        onSuccess: () => {
          update.reset()
          navigate("/tenants")
        },
      },
    )
  }

  function handleCancel() {
    update.reset()
    navigate("/tenants")
  }

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error || !tenant) {
    return (
      <div>
        <button
          onClick={() => navigate("/tenants")}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="py-20 text-center text-red-500">
          {error?.message ?? "חדר הכושר לא נמצא"}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate("/tenants")}
          className="mb-2 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{tenant.name}</h1>
        <p className="mt-1 font-mono text-xs text-gray-400" dir="ltr">
          {tenant.slug}
        </p>
      </div>

      {/* Stats */}
      <TenantStatsSection tenantId={tenant.id} />

      {/* Users */}
      <TenantUsersSection tenantId={tenant.id} />

      {/* Details / edit form */}
      <section>
        <div className="mb-4">
          <h2 className="text-lg font-bold text-gray-900">פרטי חדר כושר</h2>
          <p className="text-sm text-gray-500">עריכת פרטים כלליים</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <TenantForm
            initial={tenant}
            submitting={update.isPending}
            error={update.error ? humanizeTenantError(update.error) : null}
            submitLabel="שמור שינויים"
            onSubmit={handleSubmit}
            onCancel={handleCancel}
          />
        </div>
      </section>
    </div>
  )
}
