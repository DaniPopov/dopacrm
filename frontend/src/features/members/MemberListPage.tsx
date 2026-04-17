import { useState } from "react"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { DataTable, useRowClickNavigator } from "@/components/ui/data-table"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
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

/**
 * Members list page. Uses shared `DataTable` + `PageHeader` + `StatusBadge`
 * so the layout + status colors line up with Plans / Classes / Subscriptions.
 *
 * Member-specific bits stay local:
 * - Filter chips (search + status combo unique to this page)
 * - Avatar circle in the mobile card
 * - Cancel confirm dialog (commercial state machine + cross-concern wording)
 */
const STATUS_META: Record<MemberStatus, { label: string; variant: StatusVariant }> = {
  active: { label: "פעיל", variant: "success" },
  frozen: { label: "מוקפא", variant: "warning" },
  expired: { label: "פג תוקף", variant: "neutral" },
  cancelled: { label: "מבוטל", variant: "danger" },
}

const STATUS_ORDER: MemberStatus[] = ["active", "frozen", "expired", "cancelled"]

export default function MemberListPage() {
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<MemberStatus | null>(null)
  const [confirmCancelFor, setConfirmCancelFor] = useState<Member | null>(null)

  const {
    data: members,
    isLoading,
    error,
  } = useMembers({
    status: statusFilter ? [statusFilter] : undefined,
    search: search || undefined,
  })
  const create = useCreateMember()
  const freeze = useFreezeMember()
  const unfreeze = useUnfreezeMember()
  const cancel = useCancelMember()
  const openDetail = useRowClickNavigator<Member>((m) => `/members/${m.id}`)

  const canCancel = user?.role === "owner" || user?.role === "super_admin"

  function handleCreate(values: MemberFormValues) {
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
    : "אין מנויים עדיין. הוסיפו את הראשון!"

  return (
    <div>
      <PageHeader
        title="מנויים"
        subtitle="ניהול מנויי חדר הכושר"
        action={
          <button
            onClick={() => setShowCreate(true)}
            className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
          >
            + הוספת מנוי
          </button>
        }
      />

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

      {!isLoading && !error && (!members || members.length === 0) ? (
        <EmptyState message={emptyMessage} />
      ) : (
        <DataTable<Member>
          data={members}
          isLoading={isLoading}
          error={error}
          rowKey={(m) => m.id}
          onRowClick={openDetail}
          columns={[
            {
              header: "שם",
              cell: (m) => (
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-xs font-semibold text-white">
                    {(
                      m.first_name.charAt(0) + m.last_name.charAt(0)
                    ).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-gray-900">
                      {m.first_name} {m.last_name}
                    </div>
                    {m.email && (
                      <div
                        className="truncate font-mono text-xs text-gray-400"
                        dir="ltr"
                      >
                        {m.email}
                      </div>
                    )}
                  </div>
                </div>
              ),
              primaryMobile: true,
            },
            {
              header: "טלפון",
              cell: (m) => (
                <span className="text-gray-600" dir="ltr">
                  {m.phone}
                </span>
              ),
            },
            {
              header: "סטטוס",
              cell: (m) => (
                <StatusBadge variant={STATUS_META[m.status].variant}>
                  {STATUS_META[m.status].label}
                </StatusBadge>
              ),
            },
            {
              header: "הצטרפות",
              cell: (m) => (
                <span className="text-gray-500" dir="ltr">
                  {new Date(m.join_date).toLocaleDateString("he-IL")}
                </span>
              ),
              hideOnMobile: true,
            },
          ]}
          rowActions={[
            { label: "עריכה", onClick: openDetail },
            {
              label: "הקפאה",
              onClick: (m) => freeze.mutate({ id: m.id }),
              hidden: (m) => m.status !== "active",
            },
            {
              label: "ביטול הקפאה",
              onClick: (m) => unfreeze.mutate(m.id),
              hidden: (m) => m.status !== "frozen",
            },
            {
              label: "ביטול חברות",
              destructive: true,
              onClick: (m) => setConfirmCancelFor(m),
              hidden: (m) => !canCancel || m.status === "cancelled",
            },
          ]}
        />
      )}

      {confirmCancelFor && (
        <ConfirmDialog
          title="ביטול חברות"
          message={`האם לבטל את המנוי של ${confirmCancelFor.first_name} ${confirmCancelFor.last_name}? הנתונים יישמרו לצורכי דיווח.`}
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

/* ── Filter chip (member-specific for now) ────────────────── */

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

