import { useState } from "react"
import { humanizeTenantError } from "@/lib/api-errors"
import TenantForm, { type TenantFormValues } from "./TenantForm"
import {
  useActivateTenant,
  useCancelTenant,
  useCreateTenant,
  useSuspendTenant,
  useTenants,
  useUpdateTenant,
} from "./hooks"
import type { Tenant } from "./types"

export default function TenantListPage() {
  const { data: tenants, isLoading, error } = useTenants()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Tenant | null>(null)
  const create = useCreateTenant()
  const update = useUpdateTenant()

  function handleCreate(values: TenantFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  function handleUpdate(values: TenantFormValues) {
    if (!editing) return
    update.mutate(
      { id: editing.id, data: values },
      {
        onSuccess: () => {
          setEditing(null)
          update.reset()
        },
      },
    )
  }

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

      {/* Create form — inline card */}
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

      {/* Edit dialog — modal overlay */}
      {editing && (
        <EditDialog
          tenant={editing}
          submitting={update.isPending}
          error={update.error ? humanizeTenantError(update.error) : undefined}
          onSubmit={handleUpdate}
          onClose={() => {
            setEditing(null)
            update.reset()
          }}
        />
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
                <th className="px-5 py-3 font-medium text-gray-500">חדר כושר</th>
                <th className="px-5 py-3 font-medium text-gray-500">סטטוס</th>
                <th className="px-5 py-3 font-medium text-gray-500">טלפון</th>
                <th className="px-5 py-3 font-medium text-gray-500">עיר</th>
                <th className="px-5 py-3 font-medium text-gray-500">מטבע</th>
                <th className="px-5 py-3 font-medium text-gray-500">תאריך הצטרפות</th>
                <th className="px-5 py-3 font-medium text-gray-500">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {tenants?.map((tenant) => (
                <TenantRow key={tenant.id} tenant={tenant} onEdit={() => setEditing(tenant)} />
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
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.className}`}
    >
      {config.label}
    </span>
  )
}

/* ── Table row with actions ──────────────────────────────────── */

function TenantRow({ tenant, onEdit }: { tenant: Tenant; onEdit: () => void }) {
  const suspend = useSuspendTenant()
  const activate = useActivateTenant()
  const cancel = useCancelTenant()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const isBusy = suspend.isPending || activate.isPending || cancel.isPending

  function doAction(fn: () => void) {
    setMenuOpen(false)
    fn()
  }

  return (
    <>
      <tr className="border-b border-gray-50 transition-colors hover:bg-gray-50/50">
        <td className="px-5 py-3.5">
          <div className="flex items-center gap-3">
            {tenant.logo_presigned_url ? (
              <img
                src={tenant.logo_presigned_url}
                alt=""
                className="h-9 w-9 rounded-lg border border-gray-200 object-cover"
              />
            ) : (
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 text-xs font-semibold text-gray-400">
                {tenant.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <div className="font-medium text-gray-900">{tenant.name}</div>
              <div className="font-mono text-xs text-gray-400" dir="ltr">
                {tenant.slug}
              </div>
            </div>
          </div>
        </td>
        <td className="px-5 py-3.5">
          <StatusBadge status={tenant.status} />
        </td>
        <td className="px-5 py-3.5 text-gray-600" dir="ltr">
          {tenant.phone || "—"}
        </td>
        <td className="px-5 py-3.5 text-gray-600">{tenant.address_city || "—"}</td>
        <td className="px-5 py-3.5 text-gray-600">{tenant.currency}</td>
        <td className="px-5 py-3.5 text-gray-500" dir="ltr">
          {new Date(tenant.created_at).toLocaleDateString("he-IL")}
        </td>
        <td className="px-5 py-3.5">
          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              disabled={isBusy}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              {isBusy ? "..." : "פעולות ▾"}
            </button>
            {menuOpen && (
              <div
                className="absolute left-0 top-full z-10 mt-1 min-w-[140px] rounded-lg border border-gray-200 bg-white py-1 text-right shadow-lg"
                onMouseLeave={() => setMenuOpen(false)}
              >
                <MenuItem label="עריכה" onClick={() => doAction(onEdit)} />
                {(tenant.status === "suspended" ||
                  tenant.status === "trial" ||
                  tenant.status === "cancelled") && (
                  <MenuItem
                    label="הפעל"
                    onClick={() => doAction(() => activate.mutate(tenant.id))}
                  />
                )}
                {(tenant.status === "active" || tenant.status === "trial") && (
                  <MenuItem
                    label="השהה"
                    onClick={() => doAction(() => suspend.mutate(tenant.id))}
                  />
                )}
                {tenant.status !== "cancelled" && (
                  <MenuItem
                    label="ביטול (מחיקה רכה)"
                    variant="danger"
                    onClick={() => doAction(() => setConfirmCancel(true))}
                  />
                )}
              </div>
            )}
          </div>
        </td>
      </tr>

      {/* Confirmation modal for cancel */}
      {confirmCancel && (
        <ConfirmDialog
          title="ביטול חדר כושר"
          message={`האם לבטל את "${tenant.name}"? הנתונים יישמרו וניתן להפעיל מחדש.`}
          confirmLabel="כן, בטל"
          variant="danger"
          onConfirm={() => {
            cancel.mutate(tenant.id, {
              onSuccess: () => setConfirmCancel(false),
            })
          }}
          onCancel={() => setConfirmCancel(false)}
          loading={cancel.isPending}
        />
      )}
    </>
  )
}

function MenuItem({
  label,
  onClick,
  variant = "default",
}: {
  label: string
  onClick: () => void
  variant?: "default" | "danger"
}) {
  const color =
    variant === "danger" ? "text-red-600 hover:bg-red-50" : "text-gray-700 hover:bg-gray-50"
  return (
    <button
      onClick={onClick}
      className={`block w-full px-4 py-2 text-sm transition-colors ${color}`}
    >
      {label}
    </button>
  )
}

/* ── Edit dialog ─────────────────────────────────────────────── */

function EditDialog({
  tenant,
  submitting,
  error,
  onSubmit,
  onClose,
}: {
  tenant: Tenant
  submitting: boolean
  error: string | undefined
  onSubmit: (values: TenantFormValues) => void
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="my-8 w-full max-w-3xl rounded-xl bg-white p-6 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">עריכת {tenant.name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>
        <TenantForm
          initial={tenant}
          submitting={submitting}
          error={error ?? null}
          submitLabel="שמור שינויים"
          onSubmit={onSubmit}
          onCancel={onClose}
        />
      </div>
    </div>
  )
}

/* ── Confirm dialog ──────────────────────────────────────────── */

function ConfirmDialog({
  title,
  message,
  confirmLabel,
  variant = "default",
  loading,
  onConfirm,
  onCancel,
}: {
  title: string
  message: string
  confirmLabel: string
  variant?: "default" | "danger"
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmColor =
    variant === "danger"
      ? "bg-red-600 hover:bg-red-700"
      : "bg-blue-600 hover:bg-blue-700"
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
        <p className="mt-2 text-sm text-gray-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            ביטול
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-lg px-5 py-2 text-sm font-semibold text-white transition-colors disabled:opacity-50 ${confirmColor}`}
          >
            {loading ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
