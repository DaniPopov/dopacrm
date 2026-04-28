import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
import { useAuth } from "@/features/auth/auth-provider"
import { humanizeLeadError } from "@/lib/api-errors"
import { ActivityForm } from "./ActivityForm"
import { ActivityTimeline } from "./ActivityTimeline"
import { ConvertLeadDialog } from "./ConvertLeadDialog"
import LeadForm, { type LeadFormValues } from "./LeadForm"
import { LostReasonDialog } from "./LostReasonDialog"
import { useLead, useSetLeadStatus, useUpdateLead } from "./hooks"
import type { LeadStatus } from "./types"

const STATUS_META: Record<
  LeadStatus,
  { label: string; variant: StatusVariant }
> = {
  new: { label: "חדש", variant: "primary" },
  contacted: { label: "נוצר קשר", variant: "info" },
  trial: { label: "ניסיון", variant: "warning" },
  converted: { label: "הומר", variant: "success" },
  lost: { label: "אבוד", variant: "danger" },
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [editing, setEditing] = useState(false)
  const [showConvert, setShowConvert] = useState(false)
  const [pendingLost, setPendingLost] = useState(false)
  const [confirmReopen, setConfirmReopen] = useState(false)

  const { data: lead, isLoading, error } = useLead(id ?? "")
  const update = useUpdateLead()
  const setStatus = useSetLeadStatus()

  const canMutate =
    user?.role === "owner" || user?.role === "sales" || user?.role === "super_admin"

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error || !lead) {
    return (
      <div>
        <button
          onClick={() => navigate("/leads")}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {humanizeLeadError(error)}
        </div>
      </div>
    )
  }

  function handleEdit(values: LeadFormValues) {
    if (!lead) return
    update.mutate(
      { id: lead.id, data: values },
      {
        onSuccess: () => {
          setEditing(false)
          update.reset()
        },
      },
    )
  }

  function handleLost(reason: string) {
    if (!lead) return
    setStatus.mutate(
      {
        id: lead.id,
        data: { new_status: "lost", lost_reason: reason || null },
      },
      {
        onSettled: () => setPendingLost(false),
      },
    )
  }

  function handleReopen() {
    if (!lead) return
    setStatus.mutate(
      {
        id: lead.id,
        data: { new_status: "contacted", lost_reason: null },
      },
      {
        onSettled: () => setConfirmReopen(false),
      },
    )
  }

  const meta = STATUS_META[lead.status]
  const isOpen = lead.status !== "converted" && lead.status !== "lost"

  return (
    <div className="space-y-6">
      <div>
        <button
          onClick={() => navigate("/leads")}
          className="mb-2 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
              {lead.first_name} {lead.last_name}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-500">
              <StatusBadge variant={meta.variant}>{meta.label}</StatusBadge>
              <span dir="ltr">{lead.phone}</span>
              {lead.email && (
                <>
                  <span>·</span>
                  <span dir="ltr">{lead.email}</span>
                </>
              )}
            </div>
            {lead.lost_reason && lead.status === "lost" && (
              <div className="mt-2 text-sm text-red-700">
                סיבת אובדן: {lead.lost_reason}
              </div>
            )}
            {lead.converted_member_id && (
              <button
                onClick={() => navigate(`/members/${lead.converted_member_id}`)}
                className="mt-2 text-sm text-emerald-700 hover:underline"
              >
                → צפו במנוי שנוצר
              </button>
            )}
          </div>
          {canMutate && (
            <div className="flex flex-wrap gap-2">
              {!editing && lead.status !== "converted" && (
                <button
                  onClick={() => setEditing(true)}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  ✏️ עריכה
                </button>
              )}
              {isOpen && (
                <button
                  onClick={() => setShowConvert(true)}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
                >
                  ⏯ המר למנוי
                </button>
              )}
              {isOpen && (
                <button
                  onClick={() => setPendingLost(true)}
                  className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50"
                >
                  ✗ סמן כאבוד
                </button>
              )}
              {lead.status === "lost" && (
                <button
                  onClick={() => setConfirmReopen(true)}
                  className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-sm font-semibold text-blue-700 hover:bg-blue-50"
                >
                  ↻ פתח מחדש
                </button>
              )}
            </div>
          )}
        </div>
        {setStatus.error && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {humanizeLeadError(setStatus.error)}
          </div>
        )}
      </div>

      {editing && (
        <section className="rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <h2 className="mb-4 text-lg font-bold text-gray-900">עריכת פרטים</h2>
          <LeadForm
            initial={lead}
            submitting={update.isPending}
            error={update.error ? humanizeLeadError(update.error) : null}
            submitLabel="שמור שינויים"
            onSubmit={handleEdit}
            onCancel={() => {
              setEditing(false)
              update.reset()
            }}
          />
        </section>
      )}

      {lead.notes && !editing && (
        <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-gray-700">הערות</h2>
          <p className="whitespace-pre-wrap text-sm text-gray-900">{lead.notes}</p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-bold text-gray-900">ציר זמן</h2>
        {canMutate && lead.status !== "converted" && <ActivityForm leadId={lead.id} />}
        <ActivityTimeline leadId={lead.id} />
      </section>

      {showConvert && (
        <ConvertLeadDialog
          lead={lead}
          onSuccess={(memberId) => {
            setShowConvert(false)
            navigate(`/members/${memberId}`)
          }}
          onCancel={() => setShowConvert(false)}
        />
      )}

      {pendingLost && (
        <LostReasonDialog
          loading={setStatus.isPending}
          onConfirm={handleLost}
          onCancel={() => setPendingLost(false)}
        />
      )}

      {confirmReopen && (
        <ConfirmDialog
          title="פתיחה מחדש של ליד"
          message="הסטטוס יחזור ל'נוצר קשר'. הסיבה ההיסטורית תישאר בציר הזמן."
          confirmLabel="פתח מחדש"
          loading={setStatus.isPending}
          onConfirm={handleReopen}
          onCancel={() => setConfirmReopen(false)}
        />
      )}
    </div>
  )
}
