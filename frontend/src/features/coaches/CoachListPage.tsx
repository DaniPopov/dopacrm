import { useState } from "react"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { DataTable, useRowClickNavigator } from "@/components/ui/data-table"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeCoachError } from "@/lib/api-errors"
import CoachForm, { type CoachFormValues } from "./CoachForm"
import {
  useCancelCoach,
  useCoaches,
  useCreateCoach,
  useFreezeCoach,
  useUnfreezeCoach,
} from "./hooks"
import type { Coach, CoachStatus } from "./types"

const STATUS_META: Record<CoachStatus, { label: string; variant: StatusVariant }> = {
  active: { label: "פעיל", variant: "success" },
  frozen: { label: "מוקפא", variant: "warning" },
  cancelled: { label: "מבוטל", variant: "danger" },
}

const STATUS_ORDER: CoachStatus[] = ["active", "frozen", "cancelled"]

export default function CoachListPage() {
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<CoachStatus | null>(null)
  const [confirmCancel, setConfirmCancel] = useState<Coach | null>(null)

  const {
    data: coaches,
    isLoading,
    error,
  } = useCoaches({
    status: statusFilter ? [statusFilter] : undefined,
    search: search || undefined,
  })
  const create = useCreateCoach()
  const freeze = useFreezeCoach()
  const unfreeze = useUnfreezeCoach()
  const cancel = useCancelCoach()
  const openDetail = useRowClickNavigator<Coach>((c) => `/coaches/${c.id}`)

  const canMutate = user?.role === "owner" || user?.role === "super_admin"

  function handleCreate(values: CoachFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  const hasFilter = !!search || statusFilter !== null
  const emptyMessage = hasFilter
    ? "אין תוצאות התואמות לסינון"
    : "אין מאמנים עדיין. הוסיפו את הראשון!"

  return (
    <div>
      <PageHeader
        title="מאמנים"
        subtitle="ניהול צוות האימונים ותשלומים"
        action={
          canMutate && (
            <button
              onClick={() => setShowCreate(true)}
              className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
            >
              + הוספת מאמן
            </button>
          )
        }
      />

      {showCreate && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">מאמן חדש</h3>
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
          <CoachForm
            submitting={create.isPending}
            error={create.error ? humanizeCoachError(create.error) : null}
            submitLabel="צור מאמן"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          placeholder="חיפוש לפי שם, טלפון, או אימייל..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm outline-none transition-all placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 sm:max-w-xs"
        />
        <div className="flex flex-wrap gap-2">
          <FilterChip
            label="הכל"
            active={statusFilter === null}
            onClick={() => setStatusFilter(null)}
          />
          {STATUS_ORDER.map((s) => (
            <FilterChip
              key={s}
              label={STATUS_META[s].label}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s)}
            />
          ))}
        </div>
      </div>

      {!isLoading && !error && (!coaches || coaches.length === 0) ? (
        <EmptyState message={emptyMessage} />
      ) : (
        <DataTable<Coach>
          data={coaches}
          isLoading={isLoading}
          error={error}
          rowKey={(c) => c.id}
          onRowClick={openDetail}
          columns={[
            {
              header: "שם",
              cell: (c) => (
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 text-xs font-semibold text-white">
                    {(
                      c.first_name.charAt(0) + c.last_name.charAt(0)
                    ).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-gray-900">
                      {c.first_name} {c.last_name}
                    </div>
                    {c.email && (
                      <div
                        className="truncate font-mono text-xs text-gray-400"
                        dir="ltr"
                      >
                        {c.email}
                      </div>
                    )}
                  </div>
                </div>
              ),
              primaryMobile: true,
            },
            {
              header: "טלפון",
              cell: (c) =>
                c.phone ? (
                  <span className="text-gray-600" dir="ltr">
                    {c.phone}
                  </span>
                ) : (
                  <span className="text-gray-300">—</span>
                ),
            },
            {
              header: "סטטוס",
              cell: (c) => (
                <StatusBadge variant={STATUS_META[c.status].variant}>
                  {STATUS_META[c.status].label}
                </StatusBadge>
              ),
            },
            {
              header: "גיוס",
              cell: (c) => (
                <span className="text-gray-500" dir="ltr">
                  {new Date(c.hired_at).toLocaleDateString("he-IL")}
                </span>
              ),
              hideOnMobile: true,
            },
            {
              header: "התחברות",
              cell: (c) =>
                c.user_id ? (
                  <span className="text-xs text-emerald-600">יש</span>
                ) : (
                  <span className="text-xs text-gray-300">אין</span>
                ),
              hideOnMobile: true,
            },
          ]}
          rowActions={
            canMutate
              ? [
                  { label: "פרטים", onClick: openDetail },
                  {
                    label: "הקפאה",
                    onClick: (c) => freeze.mutate(c.id),
                    hidden: (c) => c.status !== "active",
                  },
                  {
                    label: "ביטול הקפאה",
                    onClick: (c) => unfreeze.mutate(c.id),
                    hidden: (c) => c.status !== "frozen",
                  },
                  {
                    label: "סיום העסקה",
                    destructive: true,
                    onClick: (c) => setConfirmCancel(c),
                    hidden: (c) => c.status === "cancelled",
                  },
                ]
              : []
          }
        />
      )}

      {confirmCancel && (
        <ConfirmDialog
          title="סיום העסקה"
          message={`לסיים את העסקת ${confirmCancel.first_name} ${confirmCancel.last_name}? היסטוריית המשכורות נשמרת.`}
          confirmLabel="סיים העסקה"
          destructive
          loading={cancel.isPending}
          onConfirm={() => {
            cancel.mutate(confirmCancel.id, {
              onSuccess: () => setConfirmCancel(null),
            })
          }}
          onCancel={() => setConfirmCancel(null)}
        />
      )}
    </div>
  )
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "border-blue-500 bg-blue-50 text-blue-700"
          : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
      }`}
    >
      {label}
    </button>
  )
}
