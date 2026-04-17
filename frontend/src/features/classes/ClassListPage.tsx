import { useState } from "react"
import { DataTable, useRowClickNavigator } from "@/components/ui/data-table"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeClassError } from "@/lib/api-errors"
import ClassForm, { type ClassFormValues } from "./ClassForm"
import {
  useActivateClass,
  useClasses,
  useCreateClass,
  useDeactivateClass,
} from "./hooks"
import type { GymClass } from "./types"

/**
 * Class-catalog list page — `/classes`.
 *
 * Uses shared `DataTable` + `PageHeader` + `StatusBadge` + `EmptyState`
 * primitives so the look stays consistent with other list pages. The
 * inline "create" card remains feature-local — each entity has different
 * required fields and trying to share the create form would be premature.
 */
export default function ClassListPage() {
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const {
    data: classes,
    isLoading,
    error,
  } = useClasses({ includeInactive: showInactive })
  const create = useCreateClass()
  const deactivate = useDeactivateClass()
  const activate = useActivateClass()

  const canMutate = user?.role === "owner" || user?.role === "super_admin"
  const openDetail = useRowClickNavigator<GymClass>((c) => `/classes/${c.id}`)

  function handleCreate(values: ClassFormValues) {
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
        title="סוגי שיעורים"
        subtitle="הקטלוג של סוגי השיעורים שחדר הכושר מציע"
        action={
          canMutate && !showCreate ? (
            <button
              onClick={() => setShowCreate(true)}
              className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
            >
              + הוספת סוג שיעור
            </button>
          ) : undefined
        }
      />

      {showCreate && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">סוג שיעור חדש</h3>
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
          <ClassForm
            submitting={create.isPending}
            error={create.error ? humanizeClassError(create.error) : null}
            submitLabel="צור שיעור"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      <div className="mb-4 flex items-center gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="rounded border-gray-300"
          />
          הצג שיעורים לא פעילים
        </label>
      </div>

      {!isLoading && !error && (!classes || classes.length === 0) ? (
        <EmptyState
          message={
            showInactive
              ? "אין שיעורים עדיין. הוסיפו את הראשון!"
              : "אין שיעורים פעילים. הוסיפו אחד או הציגו גם לא פעילים."
          }
        />
      ) : (
        <DataTable<GymClass>
          data={classes}
          isLoading={isLoading}
          error={error}
          rowKey={(c) => c.id}
          onRowClick={openDetail}
          columns={[
            {
              header: "שם",
              cell: (c) => <span className="font-medium text-gray-900">{c.name}</span>,
              primaryMobile: true,
            },
            {
              header: "צבע",
              cell: (c) => <ColorSwatch color={c.color} />,
            },
            {
              header: "סטטוס",
              cell: (c) => (
                <StatusBadge variant={c.is_active ? "success" : "neutral"}>
                  {c.is_active ? "פעיל" : "לא פעיל"}
                </StatusBadge>
              ),
            },
            {
              header: "תיאור",
              cell: (c) => c.description || "—",
              className: "max-w-xs truncate text-gray-600",
              hideOnMobile: true,
            },
          ]}
          rowActions={
            // Empty [] keeps the Actions column visible for staff/sales
            // with a "צפייה בלבד" placeholder per row (UX: they know the
            // column exists but isn't theirs).
            canMutate
              ? [
                  { label: "עריכה", onClick: openDetail },
                  {
                    label: "השבתה",
                    onClick: (c) => deactivate.mutate(c.id),
                    hidden: (c) => !c.is_active,
                  },
                  {
                    label: "הפעלה",
                    onClick: (c) => activate.mutate(c.id),
                    hidden: (c) => c.is_active,
                  },
                ]
              : []
          }
        />
      )}
    </div>
  )
}

/* ── Color swatch (class-specific, stays local) ───────────── */

function ColorSwatch({ color }: { color: string | null }) {
  if (!color) return <span className="text-xs text-gray-400">—</span>
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-5 w-5 flex-shrink-0 rounded border border-gray-200"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="font-mono text-xs text-gray-500" dir="ltr">
        {color}
      </span>
    </div>
  )
}
