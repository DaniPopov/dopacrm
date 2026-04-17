import { useState } from "react"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { DataTable, useRowClickNavigator } from "@/components/ui/data-table"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
import { humanizeTenantError } from "@/lib/api-errors"
import TenantForm, { type TenantFormValues } from "./TenantForm"
import {
  useActivateTenant,
  useCancelTenant,
  useCreateTenant,
  useSuspendTenant,
  useTenants,
} from "./hooks"
import type { Tenant } from "./types"

/**
 * Super-admin tenants (gyms) list page. Uses shared primitives so the
 * platform-admin view matches the gym-scoped pages visually.
 *
 * Tenant statuses map onto the shared semantic palette:
 *   trial     → primary (blue, newly-signed-up)
 *   active    → success (emerald)
 *   suspended → danger  (red, needs attention)
 *   cancelled → neutral (gray, history)
 */
const STATUS_META: Record<
  Tenant["status"],
  { label: string; variant: StatusVariant }
> = {
  active: { label: "פעיל", variant: "success" },
  trial: { label: "ניסיון", variant: "primary" },
  suspended: { label: "מושהה", variant: "danger" },
  cancelled: { label: "מבוטל", variant: "neutral" },
}

export default function TenantListPage() {
  const { data: tenants, isLoading, error } = useTenants()
  const [showCreate, setShowCreate] = useState(false)
  const [confirmCancelFor, setConfirmCancelFor] = useState<Tenant | null>(null)

  const create = useCreateTenant()
  const suspend = useSuspendTenant()
  const activate = useActivateTenant()
  const cancel = useCancelTenant()
  const openDetail = useRowClickNavigator<Tenant>((t) => `/tenants/${t.id}`)

  function handleCreate(values: TenantFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  return (
    <div>
      <PageHeader
        title="חדרי כושר"
        subtitle="ניהול כל חדרי הכושר בפלטפורמה"
        action={
          <button
            onClick={() => setShowCreate(true)}
            className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
          >
            + הוספת חדר כושר
          </button>
        }
      />

      {showCreate && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">חדר כושר חדש</h3>
            <button
              onClick={() => {
                setShowCreate(false)
                create.reset()
              }}
              className="text-gray-400 hover:text-gray-600"
              aria-label="סגירה"
            >
              ✕
            </button>
          </div>
          <TenantForm
            submitting={create.isPending}
            error={create.error ? humanizeTenantError(create.error) : null}
            submitLabel="צור חדר כושר"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      {!isLoading && !error && (!tenants || tenants.length === 0) ? (
        <EmptyState message="אין חדרי כושר עדיין. הוסיפו את הראשון!" />
      ) : (
        <DataTable<Tenant>
          data={tenants}
          isLoading={isLoading}
          error={error}
          rowKey={(t) => t.id}
          onRowClick={openDetail}
          columns={[
            {
              header: "חדר כושר",
              cell: (t) => (
                <div className="flex items-center gap-3">
                  {t.logo_presigned_url ? (
                    <img
                      src={t.logo_presigned_url}
                      alt=""
                      className="h-9 w-9 rounded-lg border border-gray-200 object-cover"
                    />
                  ) : (
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 text-xs font-semibold text-gray-400">
                      {t.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className="truncate font-medium text-gray-900">{t.name}</div>
                    <div className="truncate font-mono text-xs text-gray-400" dir="ltr">
                      {t.slug}
                    </div>
                  </div>
                </div>
              ),
              primaryMobile: true,
            },
            {
              header: "סטטוס",
              cell: (t) => (
                <StatusBadge variant={STATUS_META[t.status].variant}>
                  {STATUS_META[t.status].label}
                </StatusBadge>
              ),
            },
            {
              header: "טלפון",
              cell: (t) =>
                t.phone ? (
                  <span className="text-gray-600" dir="ltr">
                    {t.phone}
                  </span>
                ) : (
                  "—"
                ),
            },
            {
              header: "עיר",
              cell: (t) => t.address_city || "—",
              hideOnMobile: true,
            },
            {
              header: "מטבע",
              cell: (t) => t.currency,
              hideOnMobile: true,
            },
            {
              header: "תאריך הצטרפות",
              cell: (t) => (
                <span className="text-gray-500" dir="ltr">
                  {new Date(t.created_at).toLocaleDateString("he-IL")}
                </span>
              ),
              hideOnMobile: true,
            },
          ]}
          rowActions={[
            { label: "עריכה", onClick: openDetail },
            {
              label: "הפעל",
              onClick: (t) => activate.mutate(t.id),
              hidden: (t) => t.status === "active",
            },
            {
              label: "השהה",
              onClick: (t) => suspend.mutate(t.id),
              hidden: (t) => t.status !== "active" && t.status !== "trial",
            },
            {
              label: "ביטול (מחיקה רכה)",
              destructive: true,
              onClick: (t) => setConfirmCancelFor(t),
              hidden: (t) => t.status === "cancelled",
            },
          ]}
        />
      )}

      {confirmCancelFor && (
        <ConfirmDialog
          title="ביטול חדר כושר"
          message={`האם לבטל את "${confirmCancelFor.name}"? הנתונים יישמרו וניתן להפעיל מחדש.`}
          confirmLabel="כן, בטל"
          destructive
          loading={cancel.isPending}
          onConfirm={() => {
            cancel.mutate(confirmCancelFor.id, {
              onSuccess: () => setConfirmCancelFor(null),
            })
          }}
          onCancel={() => setConfirmCancelFor(null)}
        />
      )}
    </div>
  )
}
