/**
 * Schedule page — ``/schedule``.
 *
 * Owner: full edit. Week grid with navigation, three create flows
 * (recurring template, ad-hoc session, bulk range action). Click a
 * session card → side panel with cancel / swap coach.
 *
 * Coach: simplified read-only — just their own sessions in the week.
 *
 * Staff / sales: read-only week view (no create / edit buttons).
 */

import { useMemo, useState } from "react"
import { PageHeader } from "@/components/ui/page-header"
import { useAuth } from "@/features/auth/auth-provider"
import { useClasses } from "@/features/classes/hooks"
import { useCoaches } from "@/features/coaches/hooks"
import { AdHocSessionDialog } from "./AdHocSessionDialog"
import { BulkActionDialog } from "./BulkActionDialog"
import { SessionDetailPanel } from "./SessionDetailPanel"
import { TemplateForm } from "./TemplateForm"
import { TemplatesList } from "./TemplatesList"
import { WeekGrid } from "./WeekGrid"
import { useSessions } from "./hooks"
import type { ClassSession } from "./types"

export default function SchedulePage() {
  const { user } = useAuth()
  const canEdit = user?.role === "owner" || user?.role === "super_admin"

  const [weekStart, setWeekStart] = useState<Date>(() => sundayOfThisWeek())
  const [showTemplateForm, setShowTemplateForm] = useState(false)
  const [showAdHoc, setShowAdHoc] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [activeSession, setActiveSession] = useState<ClassSession | null>(null)

  const weekEnd = useMemo(() => addDays(weekStart, 7), [weekStart])

  const { data: sessions, isLoading: sessionsLoading } = useSessions({
    from: weekStart.toISOString(),
    to: weekEnd.toISOString(),
    include_cancelled: true,
  })
  const { data: classes } = useClasses({ includeInactive: true })
  const { data: coaches } = useCoaches()

  const classMap = useMemo(
    () => new Map((classes ?? []).map((c) => [c.id, c])),
    [classes],
  )
  const coachMap = useMemo(
    () => new Map((coaches ?? []).map((c) => [c.id, c])),
    [coaches],
  )

  const activeMeta = activeSession
    ? {
        className: classMap.get(activeSession.class_id)?.name ?? "שיעור",
        head: activeSession.head_coach_id
          ? coachMap.get(activeSession.head_coach_id) ?? null
          : null,
        assistant: activeSession.assistant_coach_id
          ? coachMap.get(activeSession.assistant_coach_id) ?? null
          : null,
      }
    : null

  return (
    <div>
      <PageHeader
        title="לוח שיעורים"
        subtitle={`שבוע ${formatRange(weekStart, weekEnd)}`}
        action={
          canEdit && (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setShowTemplateForm(true)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
              >
                + תבנית
              </button>
              <button
                onClick={() => setShowAdHoc(true)}
                className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100"
              >
                + חד-פעמי
              </button>
              <button
                onClick={() => setShowBulk(true)}
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                טווח תאריכים
              </button>
            </div>
          )
        }
      />

      {/* Week navigator */}
      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={() => setWeekStart(addDays(weekStart, -7))}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          ← שבוע קודם
        </button>
        <button
          onClick={() => setWeekStart(sundayOfThisWeek())}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          השבוע
        </button>
        <button
          onClick={() => setWeekStart(addDays(weekStart, 7))}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          שבוע הבא →
        </button>
      </div>

      {canEdit && (
        <TemplatesList classes={classes ?? []} coaches={coaches ?? []} />
      )}

      {sessionsLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center text-sm text-gray-400 shadow-sm">
          טוען...
        </div>
      ) : (
        <>
          {(sessions ?? []).length === 0 && (
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50/50 px-4 py-3 text-sm text-amber-800">
              אין שיעורים מתוזמנים בשבוע זה.
              {canEdit && (sessions ?? []).length === 0 && (
                <>
                  {" "}
                  צרו תבנית חדשה (+ תבנית) או נווטו לשבוע אחר ⟵
                </>
              )}
            </div>
          )}
          <WeekGrid
            weekStart={weekStart}
            sessions={sessions ?? []}
            classes={classes ?? []}
            coaches={coaches ?? []}
            onSessionClick={setActiveSession}
          />
        </>
      )}

      {showTemplateForm && (
        <TemplateForm onClose={() => setShowTemplateForm(false)} />
      )}
      {showAdHoc && <AdHocSessionDialog onClose={() => setShowAdHoc(false)} />}
      {showBulk && <BulkActionDialog onClose={() => setShowBulk(false)} />}
      {activeSession && activeMeta && (
        <SessionDetailPanel
          session={activeSession}
          className={activeMeta.className}
          headCoach={activeMeta.head}
          assistantCoach={activeMeta.assistant}
          onClose={() => setActiveSession(null)}
        />
      )}
    </div>
  )
}

// ── helpers ─────────────────────────────────────────────────────────

function sundayOfThisWeek(): Date {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  // JS: Sun=0..Sat=6 already.
  d.setDate(d.getDate() - d.getDay())
  return d
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d)
  out.setDate(out.getDate() + n)
  return out
}

function formatRange(start: Date, endExclusive: Date): string {
  const last = addDays(endExclusive, -1)
  const fmt = (x: Date) =>
    `${x.getDate()}/${x.getMonth() + 1}/${x.getFullYear()}`
  return `${fmt(start)} – ${fmt(last)}`
}
