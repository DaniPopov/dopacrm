import { useMemo, useState } from "react"
import { PageHeader } from "@/components/ui/page-header"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeLeadError } from "@/lib/api-errors"
import { KanbanBoard } from "./KanbanBoard"
import LeadForm, { type LeadFormValues } from "./LeadForm"
import { useCreateLead, useLeadStats, useLeads } from "./hooks"
import type { LeadSource, LeadStatus } from "./types"

const ALL_STATUSES: LeadStatus[] = [
  "new",
  "contacted",
  "trial",
  "converted",
  "lost",
]

export default function LeadsPage() {
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState("")
  const [sourceFilter, setSourceFilter] = useState<LeadSource | "">("")

  const canMutate =
    user?.role === "owner" || user?.role === "sales" || user?.role === "super_admin"

  const {
    data: leads,
    isLoading,
    error,
  } = useLeads({
    status: ALL_STATUSES,
    source: sourceFilter ? [sourceFilter] : undefined,
    search: search || undefined,
    limit: 200,
  })
  const { data: stats } = useLeadStats()
  const create = useCreateLead()

  const counts = useMemo(() => {
    const c: Record<LeadStatus, number> = {
      new: 0,
      contacted: 0,
      trial: 0,
      converted: 0,
      lost: 0,
    }
    if (stats?.counts) {
      for (const s of ALL_STATUSES) c[s] = stats.counts[s] ?? 0
    }
    return c
  }, [stats])

  function handleCreate(values: LeadFormValues) {
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
        title="לידים"
        subtitle="פיפליין מכירות"
        action={
          canMutate && (
            <button
              onClick={() => setShowCreate(true)}
              className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
            >
              + ליד חדש
            </button>
          )
        }
      />

      {showCreate && (
        <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">ליד חדש</h3>
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
          <LeadForm
            submitting={create.isPending}
            error={create.error ? humanizeLeadError(create.error) : null}
            submitLabel="צור ליד"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      {/* Stats banner: 30-day conversion rate. Reads from /leads/stats —
          only renders once we have a number, otherwise a hint to draw
          owners back later. */}
      {stats && stats.conversion_rate_30d !== null && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50/40 px-4 py-2 text-sm text-emerald-800">
          המרה ב-30 הימים האחרונים:{" "}
          <span className="font-bold">
            {Math.round(stats.conversion_rate_30d * 100)}%
          </span>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          placeholder="חיפוש לפי שם, טלפון, או אימייל..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm outline-none placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 sm:max-w-xs"
        />
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as LeadSource | "")}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        >
          <option value="">כל המקורות</option>
          <option value="walk_in">מזדמן</option>
          <option value="website">אתר</option>
          <option value="referral">הפניה</option>
          <option value="social_media">רשתות חברתיות</option>
          <option value="ad">פרסום</option>
          <option value="other">אחר</option>
        </select>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {humanizeLeadError(error)}
        </div>
      ) : (
        <KanbanBoard
          leads={leads ?? []}
          counts={counts}
          canMutate={!!canMutate}
        />
      )}
    </div>
  )
}
