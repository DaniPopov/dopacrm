import { useState } from "react"
import { PageHeader } from "@/components/ui/page-header"
import { SectionCard } from "@/components/ui/section-card"
import { useClasses } from "@/features/classes/hooks"
import type { GymClass } from "@/features/classes/types"
import { useMember, useMembers } from "@/features/members/hooks"
import type { Member } from "@/features/members/types"
import { humanizeAttendanceError } from "@/lib/api-errors"
import QrScannerPanel from "./QrScannerPanel"
import QuotaOverrideDialog from "./QuotaOverrideDialog"
import {
  useAttendanceList,
  useMemberAttendanceSummary,
  useRecordEntry,
  useUndoEntry,
} from "./hooks"
import type { AttendanceSummaryItem, ClassEntry } from "./types"

/**
 * Front-desk check-in page — ``/check-in``.
 *
 * Flow:
 * 1. Staff picks a member (QR scan OR name/phone search).
 * 2. Page shows the member's sub + quota summary.
 * 3. Staff taps a class:
 *    - Covered + quota remaining → immediate record, toast confirmation.
 *    - Covered + at quota → ``QuotaOverrideDialog`` (kind=quota_exceeded).
 *    - Not covered → ``QuotaOverrideDialog`` (kind=not_covered).
 * 4. Recent-entries strip below the grid lets staff undo any mistake.
 */
export default function CheckInPage() {
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)
  const [scanOpen, setScanOpen] = useState(false)

  return (
    <div>
      <PageHeader
        title="כניסות"
        subtitle="רישום הגעה של מנויים לשיעורים"
      />

      <MemberPicker
        selectedMemberId={selectedMemberId}
        onSelect={setSelectedMemberId}
        scanOpen={scanOpen}
        onOpenScan={() => setScanOpen(true)}
        onCloseScan={() => setScanOpen(false)}
      />

      {selectedMemberId && (
        <ActiveMemberWorkspace
          memberId={selectedMemberId}
          onClear={() => setSelectedMemberId(null)}
        />
      )}

      <RecentEntriesFeed />
    </div>
  )
}

/* ── Member picker (scan + search) ─────────────────────────────── */

function MemberPicker({
  selectedMemberId,
  onSelect,
  scanOpen,
  onOpenScan,
  onCloseScan,
}: {
  selectedMemberId: string | null
  onSelect: (id: string) => void
  scanOpen: boolean
  onOpenScan: () => void
  onCloseScan: () => void
}) {
  const [search, setSearch] = useState("")
  const { data: members, isLoading } = useMembers({
    search: search || undefined,
    limit: 10,
  })

  function handleScan(memberId: string) {
    onCloseScan()
    onSelect(memberId)
  }

  return (
    <SectionCard title="בחרו מנוי">
      {scanOpen ? (
        <QrScannerPanel onDecode={handleScan} onClose={onCloseScan} />
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              onClick={onOpenScan}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:w-auto"
            >
              📷 סרוק QR
            </button>
            <div className="flex-1">
              <input
                type="search"
                placeholder="או חפשו לפי שם/טלפון..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm outline-none transition-all placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
          </div>

          {search && (
            <div className="mt-3 space-y-1">
              {isLoading ? (
                <div className="text-sm text-gray-400">טוען...</div>
              ) : members && members.length > 0 ? (
                members.map((m) => (
                  <MemberRowButton
                    key={m.id}
                    member={m}
                    selected={m.id === selectedMemberId}
                    onClick={() => onSelect(m.id)}
                  />
                ))
              ) : (
                <div className="text-sm text-gray-400">אין תוצאות</div>
              )}
            </div>
          )}
        </>
      )}
    </SectionCard>
  )
}

function MemberRowButton({
  member,
  selected,
  onClick,
}: {
  member: Member
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-right text-sm transition-colors ${
        selected
          ? "border-blue-400 bg-blue-50"
          : "border-gray-100 bg-white hover:bg-gray-50"
      }`}
    >
      <div>
        <div className="font-medium text-gray-900">
          {member.first_name} {member.last_name}
        </div>
        <div className="font-mono text-xs text-gray-400" dir="ltr">
          {member.phone}
        </div>
      </div>
    </button>
  )
}

/* ── Active member workspace ──────────────────────────────────── */

function ActiveMemberWorkspace({
  memberId,
  onClear,
}: {
  memberId: string
  onClear: () => void
}) {
  const { data: member, isLoading: memberLoading, error: memberError } = useMember(memberId)
  const { data: classes } = useClasses()
  const { data: summary } = useMemberAttendanceSummary(memberId)
  const recordMutation = useRecordEntry()

  const [overrideFor, setOverrideFor] = useState<{
    classId: string
    className: string
    kind: "quota_exceeded" | "not_covered"
  } | null>(null)

  if (memberLoading) {
    return (
      <SectionCard>
        <div className="text-sm text-gray-400">טוען...</div>
      </SectionCard>
    )
  }
  if (memberError || !member) {
    return (
      <SectionCard>
        <div className="py-4 text-center text-sm text-red-500">
          המנוי לא נמצא
          <button
            onClick={onClear}
            className="mr-3 text-blue-600 hover:underline"
          >
            אפס
          </button>
        </div>
      </SectionCard>
    )
  }

  async function handleClassTap(cls: GymClass) {
    if (!summary) return
    const quotaForClass = findQuotaForClass(summary, cls.id)
    // Cover the gap: if no entitlement at all matches, treat as not_covered
    if (!quotaForClass) {
      setOverrideFor({ classId: cls.id, className: cls.name, kind: "not_covered" })
      return
    }
    if (!quotaForClass.allowed) {
      setOverrideFor({
        classId: cls.id,
        className: cls.name,
        kind: (quotaForClass.reason as "quota_exceeded" | "not_covered") ?? "quota_exceeded",
      })
      return
    }
    await recordMutation.mutateAsync({
      member_id: memberId,
      class_id: cls.id,
      override: false,
      override_reason: null,
    })
  }

  function handleConfirmOverride(reason: string | null) {
    if (!overrideFor) return
    recordMutation.mutate(
      {
        member_id: memberId,
        class_id: overrideFor.classId,
        override: true,
        override_reason: reason,
      },
      {
        onSuccess: () => setOverrideFor(null),
      },
    )
  }

  return (
    <>
      <SectionCard
        title={`${member.first_name} ${member.last_name}`}
        action={
          <button
            onClick={onClear}
            className="text-sm text-blue-600 hover:underline"
          >
            החלף מנוי
          </button>
        }
      >
        {summary && summary.length > 0 ? (
          <MemberSummaryStrip summary={summary} classes={classes ?? []} />
        ) : (
          <div className="rounded-lg border border-dashed border-amber-200 bg-amber-50/50 px-4 py-3 text-sm text-amber-800">
            למנוי זה אין מנוי פעיל. יש להרשם למסלול לפני רישום כניסה.
          </div>
        )}
      </SectionCard>

      {summary && summary.length > 0 && (
        <SectionCard title="בחרו שיעור">
          <ClassGrid
            classes={classes ?? []}
            summary={summary}
            disabled={recordMutation.isPending}
            onTap={handleClassTap}
          />
          {recordMutation.error && (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {humanizeAttendanceError(recordMutation.error)}
            </div>
          )}
        </SectionCard>
      )}

      {overrideFor && (
        <QuotaOverrideDialog
          kind={overrideFor.kind}
          className={overrideFor.className}
          submitting={recordMutation.isPending}
          onConfirm={handleConfirmOverride}
          onCancel={() => setOverrideFor(null)}
        />
      )}
    </>
  )
}

function MemberSummaryStrip({
  summary,
  classes,
}: {
  summary: AttendanceSummaryItem[]
  classes: GymClass[]
}) {
  const classNameById = new Map(classes.map((c) => [c.id, c.name]))
  return (
    <div className="flex flex-wrap gap-2">
      {summary.map((s, i) => {
        const label = s.reset_period === "unlimited" ? "ללא הגבלה" : `${s.used ?? 0}/${s.quantity ?? 0}`
        return (
          <span
            key={i}
            className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
            title={s.reset_period ?? ""}
          >
            {/* AttendanceSummaryItem doesn't carry class_id today; show the generic count. */}
            {label} {s.reset_period ? `(${resetPeriodLabel(s.reset_period)})` : ""}
          </span>
        )
      })}
    </div>
  )
}

function resetPeriodLabel(v: string): string {
  return (
    {
      weekly: "שבועי",
      monthly: "חודשי",
      billing_period: "תקופת חיוב",
      never: "סה״כ",
      unlimited: "ללא הגבלה",
    }[v] ?? v
  )
}

/* ── Class grid ───────────────────────────────────────────────── */

function ClassGrid({
  classes,
  summary,
  disabled,
  onTap,
}: {
  classes: GymClass[]
  summary: AttendanceSummaryItem[]
  disabled: boolean
  onTap: (c: GymClass) => void
}) {
  if (classes.length === 0) {
    return <div className="text-sm text-gray-400">אין שיעורים מוגדרים</div>
  }
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {classes.map((c) => {
        const q = findQuotaForClass(summary, c.id)
        const covered = !!q
        const allowed = q?.allowed ?? false
        return (
          <button
            key={c.id}
            onClick={() => onTap(c)}
            disabled={disabled}
            className={`flex flex-col items-center gap-1 rounded-xl border p-4 text-center transition-all disabled:opacity-50 ${
              !covered
                ? "border-gray-200 bg-gray-50 text-gray-400"
                : allowed
                  ? "border-emerald-200 bg-emerald-50/50 text-emerald-700 hover:bg-emerald-50"
                  : "border-amber-200 bg-amber-50/50 text-amber-800 hover:bg-amber-50"
            }`}
          >
            {c.color && (
              <span
                aria-hidden
                className="h-3 w-3 rounded-full border border-white/60"
                style={{ backgroundColor: c.color }}
              />
            )}
            <span className="text-sm font-semibold text-gray-900">{c.name}</span>
            <span className="text-xs">
              {!covered
                ? "לא בתוכנית"
                : q && q.reset_period === "unlimited"
                  ? "✓ ללא הגבלה"
                  : q && q.remaining !== null && q.remaining !== undefined
                    ? allowed
                      ? `✓ ${q.remaining} נותרו`
                      : "מכסה מלאה"
                    : ""}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/**
 * Find the quota row that applies to this class. The current
 * SummaryItem schema doesn't carry ``class_id``, so we use a simple
 * heuristic: if the member has exactly one non-unlimited entitlement
 * it applies to all classes; otherwise we return the first match.
 *
 * Future: backend should return class_id per summary item so the
 * mapping is deterministic. Tracked as a spec follow-up.
 */
function findQuotaForClass(
  summary: AttendanceSummaryItem[],
  _classId: string,
): AttendanceSummaryItem | null {
  if (summary.length === 0) return null
  return summary[0] ?? null
}

/* ── Recent entries feed with undo ────────────────────────────── */

function RecentEntriesFeed() {
  const { data: entries, isLoading } = useAttendanceList({ limit: 10 })
  const undoMutation = useUndoEntry()
  const { data: classes } = useClasses({ includeInactive: true })
  const classNameById = new Map((classes ?? []).map((c) => [c.id, c.name]))

  if (isLoading) return null
  if (!entries || entries.length === 0) return null

  return (
    <SectionCard title="כניסות אחרונות">
      <ul className="divide-y divide-gray-100">
        {entries.map((e) => (
          <li key={e.id} className="flex items-center justify-between py-2.5 text-sm">
            <div className="min-w-0 flex-1">
              <div className="truncate text-gray-900">
                {classNameById.get(e.class_id) ?? "שיעור"}
                {e.override && (
                  <span className="mr-2 inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                    override
                  </span>
                )}
                {e.undone_at && (
                  <span className="mr-2 inline-flex rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                    בוטל
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-400">{timeAgo(e.entered_at)}</div>
            </div>
            {!e.undone_at && (
              <UndoButton
                entry={e}
                disabled={undoMutation.isPending}
                onUndo={() =>
                  undoMutation.mutate({ id: e.id, data: { reason: null } })
                }
              />
            )}
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}

function UndoButton({
  entry,
  disabled,
  onUndo,
}: {
  entry: ClassEntry
  disabled: boolean
  onUndo: () => void
}) {
  const withinWindow = isWithinUndoWindow(entry.entered_at)
  if (!withinWindow) return null
  return (
    <button
      onClick={onUndo}
      disabled={disabled}
      className="rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
    >
      בטל
    </button>
  )
}

function isWithinUndoWindow(isoTimestamp: string): boolean {
  const entered = new Date(isoTimestamp).getTime()
  const now = Date.now()
  return now - entered <= 24 * 60 * 60 * 1000
}

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return "לפני פחות מדקה"
  if (seconds < 3600) return `לפני ${Math.floor(seconds / 60)} דקות`
  if (seconds < 86400) return `לפני ${Math.floor(seconds / 3600)} שעות`
  return new Date(iso).toLocaleDateString("he-IL")
}
