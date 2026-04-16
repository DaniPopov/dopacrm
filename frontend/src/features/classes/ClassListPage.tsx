import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useDevice } from "@/hooks/useDevice"
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
 * Owner defines the gym's class types here (Spinning, Yoga, CrossFit…).
 * Staff/sales can view the catalog but not mutate.
 *
 * Layout: table on desktop, cards on mobile. Each row shows name,
 * color swatch, status badge, description snippet, and (for owner)
 * an actions dropdown with Edit / Deactivate / Activate.
 */
export default function ClassListPage() {
  const { isMobile } = useDevice()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const { data: classes, isLoading, error } = useClasses({
    includeInactive: showInactive,
  })
  const create = useCreateClass()

  const canMutate = user?.role === "owner" || user?.role === "super_admin"

  function handleCreate(values: ClassFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  function openDetail(cls: GymClass) {
    navigate(`/classes/${cls.id}`)
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            סוגי שיעורים
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            הקטלוג של סוגי השיעורים שחדר הכושר מציע
          </p>
        </div>
        {canMutate && !showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
          >
            + הוספת סוג שיעור
          </button>
        )}
      </div>

      {/* Create form — inline */}
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

      {/* Include-inactive toggle */}
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

      {/* List */}
      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="py-20 text-center text-red-500">{error.message}</div>
      ) : !classes || classes.length === 0 ? (
        <EmptyState showInactive={showInactive} />
      ) : isMobile ? (
        <div className="space-y-3">
          {classes.map((c) => (
            <ClassCard
              key={c.id}
              cls={c}
              canMutate={canMutate}
              onOpen={() => openDetail(c)}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="rounded-tr-xl px-5 py-3 font-medium text-gray-500">שם</th>
                <th className="px-5 py-3 font-medium text-gray-500">צבע</th>
                <th className="px-5 py-3 font-medium text-gray-500">סטטוס</th>
                <th className="px-5 py-3 font-medium text-gray-500">תיאור</th>
                <th className="rounded-tl-xl px-5 py-3 font-medium text-gray-500">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => (
                <ClassRow
                  key={c.id}
                  cls={c}
                  canMutate={canMutate}
                  onOpen={() => openDetail(c)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────── */

function EmptyState({ showInactive }: { showInactive: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-16 text-center text-sm text-gray-400">
      {showInactive
        ? "אין שיעורים עדיין. הוסיפו את הראשון!"
        : "אין שיעורים פעילים. הוסיפו אחד או הציגו גם לא פעילים."}
    </div>
  )
}

/* ── Status badge ─────────────────────────────────────────── */

function StatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
      פעיל
    </span>
  ) : (
    <span className="inline-flex rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-500">
      לא פעיל
    </span>
  )
}

/* ── Color swatch ─────────────────────────────────────────── */

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

/* ── Table row ───────────────────────────────────────────── */

function ClassRow({
  cls,
  canMutate,
  onOpen,
}: {
  cls: GymClass
  canMutate: boolean
  onOpen: () => void
}) {
  return (
    <tr className="border-b border-gray-50 transition-colors hover:bg-gray-50/50">
      <td className="px-5 py-3.5">
        <button onClick={onOpen} className="text-right hover:underline">
          <div className="font-medium text-gray-900">{cls.name}</div>
        </button>
      </td>
      <td className="px-5 py-3.5">
        <ColorSwatch color={cls.color} />
      </td>
      <td className="px-5 py-3.5">
        <StatusBadge isActive={cls.is_active} />
      </td>
      <td className="max-w-xs truncate px-5 py-3.5 text-gray-600">
        {cls.description || "—"}
      </td>
      <td className="px-5 py-3.5">
        <ClassActions cls={cls} canMutate={canMutate} onEdit={onOpen} />
      </td>
    </tr>
  )
}

/* ── Mobile card ─────────────────────────────────────────── */

function ClassCard({
  cls,
  canMutate,
  onOpen,
}: {
  cls: GymClass
  canMutate: boolean
  onOpen: () => void
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div
          className="h-10 w-10 flex-shrink-0 rounded-lg border border-gray-200"
          style={{ backgroundColor: cls.color ?? "#E5E7EB" }}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <button onClick={onOpen} className="min-w-0 flex-1 text-right">
              <div className="truncate font-semibold text-gray-900">{cls.name}</div>
              {cls.description && (
                <div className="truncate text-xs text-gray-500">{cls.description}</div>
              )}
            </button>
            <StatusBadge isActive={cls.is_active} />
          </div>
        </div>
      </div>
      <div className="mt-3 border-t border-gray-100 pt-3">
        <ClassActions cls={cls} canMutate={canMutate} onEdit={onOpen} />
      </div>
    </div>
  )
}

/* ── Actions dropdown ────────────────────────────────────── */

/**
 * Action menu — only rendered for owner/super_admin. For staff/sales
 * it renders a disabled placeholder or nothing at all.
 */
function ClassActions({
  cls,
  canMutate,
  onEdit,
}: {
  cls: GymClass
  canMutate: boolean
  onEdit: () => void
}) {
  const deactivate = useDeactivateClass()
  const activate = useActivateClass()
  const [menuOpen, setMenuOpen] = useState(false)

  const isBusy = deactivate.isPending || activate.isPending

  if (!canMutate) {
    return <span className="text-xs text-gray-400">צפייה בלבד</span>
  }

  function doAction(fn: () => void) {
    setMenuOpen(false)
    fn()
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMenuOpen((v) => !v)}
        disabled={isBusy}
        className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50 sm:w-auto"
      >
        {isBusy ? "..." : "פעולות ▾"}
      </button>
      {menuOpen && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 min-w-[140px] rounded-lg border border-gray-200 bg-white py-1 text-right shadow-lg sm:right-auto">
          <MenuItem label="עריכה" onClick={() => doAction(onEdit)} />
          {cls.is_active ? (
            <MenuItem
              label="השבתה"
              onClick={() => doAction(() => deactivate.mutate(cls.id))}
            />
          ) : (
            <MenuItem
              label="הפעלה"
              onClick={() => doAction(() => activate.mutate(cls.id))}
            />
          )}
        </div>
      )}
    </div>
  )
}

/** Single menu item — plain color for normal actions. */
function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="block w-full px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
    >
      {label}
    </button>
  )
}
