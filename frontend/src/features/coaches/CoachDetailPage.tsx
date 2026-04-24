import { useState } from "react"
import { useParams, Link } from "react-router-dom"
import { PageHeader } from "@/components/ui/page-header"
import { SectionCard } from "@/components/ui/section-card"
import { StatusBadge } from "@/components/ui/status-badge"
import { useAuth } from "@/features/auth/auth-provider"
import { useClasses } from "@/features/classes/hooks"
import { humanizeCoachError } from "@/lib/api-errors"
import CoachForm, { type CoachFormValues } from "./CoachForm"
import { EarningsCard, formatMoney, payModelLabel } from "./EarningsCard"
import {
  useClassesForCoach,
  useCoach,
  useCoachEarnings,
  useInviteCoachUser,
  useUpdateCoach,
} from "./hooks"
import type { Coach, CoachStatus } from "./types"

/**
 * Coach detail page — ``/coaches/:id``.
 *
 * Sections:
 * 1. Header (name + status + actions).
 * 2. Edit form + invite-user button (owner+ only).
 * 3. Earnings card (current month by default).
 * 4. Classes this coach teaches.
 */
export default function CoachDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const canEdit = user?.role === "owner" || user?.role === "super_admin"

  const { data: coach, isLoading, error } = useCoach(id ?? "")
  const [editing, setEditing] = useState(false)

  if (isLoading) {
    return (
      <div>
        <PageHeader title="מאמן" />
        <SectionCard>
          <div className="text-sm text-gray-400">טוען...</div>
        </SectionCard>
      </div>
    )
  }
  if (error || !coach) {
    return (
      <div>
        <PageHeader title="מאמן" />
        <SectionCard>
          <div className="py-6 text-center text-sm text-red-500">
            המאמן לא נמצא
            <Link to="/coaches" className="mr-3 text-blue-600 hover:underline">
              חזרה לרשימה
            </Link>
          </div>
        </SectionCard>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title={`${coach.first_name} ${coach.last_name}`}
        subtitle={statusLabel(coach.status)}
        action={
          <div className="flex items-center gap-3">
            <StatusBadge variant={statusVariant(coach.status)}>
              {statusLabel(coach.status)}
            </StatusBadge>
            {canEdit && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                עריכה
              </button>
            )}
          </div>
        }
      />

      {editing && canEdit && (
        <EditCoachCard
          coach={coach}
          onDone={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      )}

      <CurrentMonthEarnings coachId={coach.id} />
      <CoachClassesSection coachId={coach.id} />
      {canEdit && !coach.user_id && <InviteLoginSection coachId={coach.id} />}
    </div>
  )
}

/* ── Edit form ──────────────────────────────────────────────────────── */

function EditCoachCard({
  coach,
  onDone,
  onCancel,
}: {
  coach: Coach
  onDone: () => void
  onCancel: () => void
}) {
  const update = useUpdateCoach()
  function handle(values: CoachFormValues) {
    update.mutate(
      { id: coach.id, data: values },
      { onSuccess: () => onDone() },
    )
  }
  return (
    <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
      <h3 className="mb-4 text-lg font-bold text-gray-900">עריכת פרטי מאמן</h3>
      <CoachForm
        initial={coach}
        submitting={update.isPending}
        error={update.error ? humanizeCoachError(update.error) : null}
        submitLabel="שמירה"
        onSubmit={handle}
        onCancel={onCancel}
      />
    </div>
  )
}

/* ── Current-month earnings section ────────────────────────────────── */

function CurrentMonthEarnings({ coachId }: { coachId: string }) {
  const [range] = useState(() => currentMonthRange())
  const { data, isLoading } = useCoachEarnings(coachId, range.from, range.to)
  if (isLoading) {
    return (
      <SectionCard title="הכנסה משוערת — חודש נוכחי">
        <div className="text-sm text-gray-400">טוען...</div>
      </SectionCard>
    )
  }
  if (!data) return null
  return (
    <EarningsCard data={data} title={`הכנסה משוערת — ${range.from} עד ${range.to}`} />
  )
}

function currentMonthRange() {
  const now = new Date()
  const first = new Date(now.getFullYear(), now.getMonth(), 1)
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { from: fmt(first), to: fmt(last) }
}

/* ── Classes this coach teaches ────────────────────────────────────── */

function CoachClassesSection({ coachId }: { coachId: string }) {
  const { data: links, isLoading } = useClassesForCoach(coachId, false)
  const { data: classes } = useClasses({ includeInactive: true })
  const classNameById = new Map((classes ?? []).map((c) => [c.id, c.name]))

  if (isLoading) {
    return (
      <SectionCard title="שיעורים">
        <div className="text-sm text-gray-400">טוען...</div>
      </SectionCard>
    )
  }
  if (!links || links.length === 0) {
    return (
      <SectionCard title="שיעורים">
        <div className="text-sm text-gray-400">
          המאמן אינו משויך עדיין לשיעור כלשהו. שיוך נעשה מתוך דף שיעור.
        </div>
      </SectionCard>
    )
  }
  return (
    <SectionCard title="שיעורים">
      <ul className="divide-y divide-gray-100">
        {links.map((link) => (
          <li key={link.id} className="py-3">
            <div className="flex items-center justify-between">
              <div>
                <Link
                  to={`/classes/${link.class_id}`}
                  className="font-medium text-gray-900 hover:underline"
                >
                  {classNameById.get(link.class_id) ?? "שיעור"}
                </Link>
                <div className="text-xs text-gray-400">
                  {link.role} · {payModelLabel(link.pay_model)} ·{" "}
                  <span dir="ltr">
                    {formatMoney(link.pay_amount_cents, "ILS")}
                  </span>
                </div>
              </div>
              <div className="text-xs text-gray-400">
                {link.weekdays.length === 0
                  ? "כל הימים"
                  : link.weekdays.join(", ")}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}

/* ── Invite login ──────────────────────────────────────────────────── */

function InviteLoginSection({ coachId }: { coachId: string }) {
  const invite = useInviteCoachUser()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  function handle(e: React.FormEvent) {
    e.preventDefault()
    invite.mutate(
      { id: coachId, data: { email, password } },
      {
        onSuccess: () => {
          setEmail("")
          setPassword("")
        },
      },
    )
  }

  return (
    <SectionCard title="הזמנה למערכת">
      <p className="mb-4 text-sm text-gray-500">
        יצירת משתמש למאמן כדי שיוכל להיכנס למערכת ולצפות בשיעורים ובהכנסות שלו.
      </p>
      <form onSubmit={handle} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
        <input
          type="email"
          placeholder="אימייל"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          dir="ltr"
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        />
        <input
          type="password"
          placeholder="סיסמה ראשונית (8+ תווים)"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          dir="ltr"
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        />
        <button
          type="submit"
          disabled={invite.isPending}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {invite.isPending ? "שולח..." : "שלח הזמנה"}
        </button>
      </form>
      {invite.error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {humanizeCoachError(invite.error)}
        </div>
      )}
    </SectionCard>
  )
}

/* ── Small helpers ─────────────────────────────────────────────────── */

function statusLabel(s: CoachStatus) {
  return { active: "פעיל", frozen: "מוקפא", cancelled: "מבוטל" }[s] ?? s
}

function statusVariant(s: CoachStatus): "success" | "warning" | "danger" {
  return { active: "success", frozen: "warning", cancelled: "danger" }[
    s
  ] as "success" | "warning" | "danger"
}
