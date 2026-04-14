import { useNavigate, useParams } from "react-router-dom"
import { humanizeTenantError } from "@/lib/api-errors"
import TenantForm, { type TenantFormValues } from "./TenantForm"
import { useTenant, useUpdateTenant } from "./hooks"

/**
 * Tenant edit page — `/tenants/:id`.
 *
 * Opened from the "עריכה" action in the tenant list. On save, navigates
 * back to `/tenants`. On cancel, same thing. Fetching is handled by
 * TanStack Query; the list's cache already has the tenant in most cases
 * so this page loads instantly.
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
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            onClick={() => navigate("/tenants")}
            className="mb-1 text-sm text-blue-600 hover:underline"
          >
            ← חזרה לרשימה
          </button>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            עריכת {tenant.name}
          </h1>
          <p className="mt-1 font-mono text-xs text-gray-400" dir="ltr">
            {tenant.slug}
          </p>
        </div>
      </div>

      {/* Form */}
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
    </div>
  )
}
