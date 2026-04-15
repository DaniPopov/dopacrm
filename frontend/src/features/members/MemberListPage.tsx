import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useDevice } from "@/hooks/useDevice"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeMemberError } from "@/lib/api-errors"
import MemberForm, { type MemberFormValues } from "./MemberForm"
import {
  useCancelMember,
  useCreateMember,
  useFreezeMember,
  useMembers,
  useUnfreezeMember,
} from "./hooks"
import type { Member, MemberStatus } from "./types"

/** Hebrew labels for each lifecycle state (used by badge + filter chips). */
const STATUS_CONFIG: Record<
  MemberStatus,
  { label: string; className: string }
> = {
  active: { label: "פעיל", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  frozen: { label: "מוקפא", className: "bg-blue-50 text-blue-700 border-blue-200" },
  cancelled: { label: "מבוטל", className: "bg-gray-50 text-gray-500 border-gray-200" },
  expired: { label: "פג תוקף", className: "bg-amber-50 text-amber-700 border-amber-200" },
}

const STATUS_ORDER: MemberStatus[] = ["active", "frozen", "expired", "cancelled"]

/**
 * Members list page — the gym's customer roster.
 *
 * Layout:
 * - Desktop/tablet: table with columns (name, phone, status, join date, actions)
 * - Mobile: stacked cards with the same data
 *
 * Interactions:
 * - Search (debounced via query-key — TanStack Query caches per filter combo)
 * - Status filter chips (active/frozen/expired/cancelled)
 * - Inline "+ הוסף מנוי" panel using MemberForm
 * - Row actions dropdown: Edit (→ /members/:id), Freeze/Unfreeze, Cancel
 */
export default function MemberListPage() {
  const { isMobile } = useDevice()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<MemberStatus | null>(null)

  const { data: members, isLoading, error } = useMembers({
    status: statusFilter ? [statusFilter] : undefined,
    search: search || undefined,
  })
  const create = useCreateMember()

  function handleCreate(values: MemberFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  function openDetail(member: Member) {
    navigate(`/members/${member.id}`)
  }

  return (
    <div>
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">מנויים</h1>
          <p className="mt-1 text-sm text-gray-500">ניהול מנויי חדר הכושר</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
        >
          + הוספת מנוי
        </button>
      </div>

      {/* ── Create form — inline card ──────────────────────── */}
      {showCreate && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">מנוי חדש</h3>
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
          <MemberForm
            submitting={create.isPending}
            error={create.error ? humanizeMemberError(create.error) : null}
            submitLabel="צור מנוי"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      {/* ── Filters ─────────────────────────────────────────── */}
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
              label={STATUS_CONFIG[s].label}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s)}
            />
          ))}
        </div>
      </div>

      {/* ── List ────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="py-20 text-center text-red-500">{error.message}</div>
      ) : !members || members.length === 0 ? (
        <EmptyState search={search} statusFilter={statusFilter} />
      ) : isMobile ? (
        <div className="space-y-3">
          {members.map((m) => (
            <MemberCard key={m.id} member={m} onOpen={() => openDetail(m)} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="rounded-tr-xl px-5 py-3 font-medium text-gray-500">שם</th>
                <th className="px-5 py-3 font-medium text-gray-500">טלפון</th>
                <th className="px-5 py-3 font-medium text-gray-500">סטטוס</th>
                <th className="px-5 py-3 font-medium text-gray-500">הצטרפות</th>
                <th className="rounded-tl-xl px-5 py-3 font-medium text-gray-500">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <MemberRow key={m.id} member={m} onOpen={() => openDetail(m)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ── Filter chip ──────────────────────────────────────────── */

/**
 * A toggleable pill for filtering by status (or clearing via "הכל").
 * Controlled by the parent — just reports clicks.
 */
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

/* ── Status badge ──────────────────────────────────────────── */

/**
 * Pill showing the member's lifecycle state with a Hebrew label
 * and a color matching the state (emerald=active, blue=frozen, …).
 */
function StatusBadge({ status }: { status: MemberStatus }) {
  const c = STATUS_CONFIG[status]
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${c.className}`}
    >
      {c.label}
    </span>
  )
}

/* ── Empty state ──────────────────────────────────────────── */

/**
 * Shown when the list is empty — different copy depending on whether
 * the user has filters/search applied vs a truly empty gym.
 */
function EmptyState({
  search,
  statusFilter,
}: {
  search: string
  statusFilter: MemberStatus | null
}) {
  const hasFilter = !!search || statusFilter !== null
  return (
    <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-16 text-center text-sm text-gray-400">
      {hasFilter ? "אין תוצאות התואמות לסינון" : "אין מנויים עדיין. הוסיפו את הראשון!"}
    </div>
  )
}

/* ── Table row (desktop) ──────────────────────────────────── */

/**
 * One row of the desktop table — name + phone + status badge + join
 * date + "פעולות" dropdown with status-dependent actions.
 */
function MemberRow({ member, onOpen }: { member: Member; onOpen: () => void }) {
  return (
    <tr className="border-b border-gray-50 transition-colors hover:bg-gray-50/50">
      <td className="px-5 py-3.5">
        <button onClick={onOpen} className="text-right hover:underline">
          <div className="font-medium text-gray-900">
            {member.first_name} {member.last_name}
          </div>
          {member.email && (
            <div className="font-mono text-xs text-gray-400" dir="ltr">
              {member.email}
            </div>
          )}
        </button>
      </td>
      <td className="px-5 py-3.5 text-gray-600" dir="ltr">
        {member.phone}
      </td>
      <td className="px-5 py-3.5">
        <StatusBadge status={member.status} />
      </td>
      <td className="px-5 py-3.5 text-gray-500" dir="ltr">
        {new Date(member.join_date).toLocaleDateString("he-IL")}
      </td>
      <td className="px-5 py-3.5">
        <MemberActions member={member} onEdit={onOpen} />
      </td>
    </tr>
  )
}

/* ── Mobile card ──────────────────────────────────────────── */

/**
 * Mobile-friendly member card replacing the table row on < 768px.
 * Compact stack: avatar + name + status, then phone, then actions.
 */
function MemberCard({ member, onOpen }: { member: Member; onOpen: () => void }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-sm font-semibold text-white">
          {(member.first_name.charAt(0) + member.last_name.charAt(0)).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <button onClick={onOpen} className="min-w-0 flex-1 text-right">
              <div className="truncate font-semibold text-gray-900">
                {member.first_name} {member.last_name}
              </div>
              <div className="truncate text-xs text-gray-500" dir="ltr">
                {member.phone}
              </div>
            </button>
            <StatusBadge status={member.status} />
          </div>
        </div>
      </div>
      <div className="mt-3 border-t border-gray-100 pt-3">
        <MemberActions member={member} onEdit={onOpen} />
      </div>
    </div>
  )
}

/* ── Actions dropdown ─────────────────────────────────────── */

/**
 * "פעולות" dropdown — shows status-dependent options:
 *  - active    → Edit, Freeze, Cancel (owner only)
 *  - frozen    → Edit, Unfreeze, Cancel (owner only)
 *  - cancelled → Edit only
 *  - expired   → Edit, Cancel (owner only)
 *
 * Cancel opens a ConfirmDialog. Freeze/Unfreeze fire immediately.
 */
function MemberActions({
  member,
  onEdit,
}: {
  member: Member
  onEdit: () => void
}) {
  const { user } = useAuth()
  const freeze = useFreezeMember()
  const unfreeze = useUnfreezeMember()
  const cancel = useCancelMember()
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)

  const isBusy = freeze.isPending || unfreeze.isPending || cancel.isPending
  const canCancel = user?.role === "owner" || user?.role === "super_admin"

  function doAction(fn: () => void) {
    setMenuOpen(false)
    fn()
  }

  return (
    <>
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
            {member.status === "active" && (
              <MenuItem
                label="הקפאה"
                onClick={() => doAction(() => freeze.mutate({ id: member.id }))}
              />
            )}
            {member.status === "frozen" && (
              <MenuItem
                label="ביטול הקפאה"
                onClick={() => doAction(() => unfreeze.mutate(member.id))}
              />
            )}
            {canCancel && member.status !== "cancelled" && (
              <MenuItem
                label="ביטול חברות"
                variant="danger"
                onClick={() => doAction(() => setConfirmCancel(true))}
              />
            )}
          </div>
        )}
      </div>

      {confirmCancel && (
        <ConfirmDialog
          title="ביטול חברות"
          message={`האם לבטל את המנוי של ${member.first_name} ${member.last_name}? הנתונים יישמרו לצורכי דיווח.`}
          confirmLabel="כן, בטל"
          variant="danger"
          loading={cancel.isPending}
          onConfirm={() => {
            cancel.mutate(member.id, { onSuccess: () => setConfirmCancel(false) })
          }}
          onCancel={() => setConfirmCancel(false)}
        />
      )}
    </>
  )
}

/**
 * Single clickable item in the actions dropdown.
 * `variant="danger"` styles it red for destructive actions (cancel).
 */
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

/* ── Confirm dialog ───────────────────────────────────────── */

/**
 * Generic yes/cancel modal. Clicks on the backdrop dismiss.
 * `variant="danger"` paints the confirm button red.
 */
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
    variant === "danger" ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
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
