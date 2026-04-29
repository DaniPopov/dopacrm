import { useMemo, useState } from "react"
import { humanizeLeadError } from "@/lib/api-errors"
import { LeadCard } from "./LeadCard"
import { LostReasonDialog } from "./LostReasonDialog"
import { useSetLeadStatus } from "./hooks"
import type { Lead, LeadStatus } from "./types"

const COLUMNS: { status: LeadStatus; label: string; tint: string }[] = [
  { status: "new", label: "חדש", tint: "bg-blue-50/50 border-blue-200" },
  { status: "contacted", label: "נוצר קשר", tint: "bg-indigo-50/50 border-indigo-200" },
  { status: "trial", label: "ניסיון", tint: "bg-amber-50/50 border-amber-200" },
  {
    status: "converted",
    label: "הומר",
    tint: "bg-emerald-50/50 border-emerald-200",
  },
  { status: "lost", label: "אבוד", tint: "bg-red-50/50 border-red-200" },
]

interface Props {
  leads: Lead[]
  counts: Record<LeadStatus, number>
  canMutate: boolean
}

export function KanbanBoard({ leads, counts, canMutate }: Props) {
  const setStatus = useSetLeadStatus()
  const [dragLead, setDragLead] = useState<Lead | null>(null)
  const [hoverColumn, setHoverColumn] = useState<LeadStatus | null>(null)
  const [pendingLost, setPendingLost] = useState<Lead | null>(null)

  // Bucket leads by status. Keep original order (newest first).
  const buckets = useMemo(() => {
    const map: Record<LeadStatus, Lead[]> = {
      new: [],
      contacted: [],
      trial: [],
      converted: [],
      lost: [],
    }
    for (const lead of leads) map[lead.status].push(lead)
    return map
  }, [leads])

  function handleDrop(target: LeadStatus, e: React.DragEvent) {
    e.preventDefault()
    setHoverColumn(null)
    if (!dragLead || !canMutate) return
    if (dragLead.status === target) return
    // Drop-on-converted not allowed via drag — must use the convert dialog.
    if (target === "converted") return
    if (target === "lost") {
      setPendingLost(dragLead)
      return
    }
    setStatus.mutate({
      id: dragLead.id,
      data: { new_status: target, lost_reason: null },
    })
  }

  function confirmLost(reason: string) {
    if (!pendingLost) return
    setStatus.mutate(
      {
        id: pendingLost.id,
        data: { new_status: "lost", lost_reason: reason || null },
      },
      {
        onSettled: () => setPendingLost(null),
      },
    )
  }

  return (
    <>
      {setStatus.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {humanizeLeadError(setStatus.error)}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-5">
        {COLUMNS.map((col) => {
          const dropDisabled = !canMutate || col.status === "converted"
          const isHover = hoverColumn === col.status
          return (
            <div
              key={col.status}
              onDragOver={(e) => {
                if (dropDisabled) return
                e.preventDefault()
                setHoverColumn(col.status)
              }}
              onDragLeave={() => {
                if (hoverColumn === col.status) setHoverColumn(null)
              }}
              onDrop={(e) => handleDrop(col.status, e)}
              className={`rounded-xl border-2 ${col.tint} p-3 transition-all ${
                isHover ? "ring-2 ring-blue-400" : ""
              } ${dropDisabled ? "opacity-90" : ""}`}
            >
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">{col.label}</h3>
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-medium text-gray-600">
                  {counts[col.status] ?? 0}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                {buckets[col.status].length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-200 bg-white/30 p-3 text-center text-xs text-gray-400">
                    {col.status === "converted"
                      ? "השתמשו בכפתור 'המר למנוי' בכרטיס הליד"
                      : "אין לידים"}
                  </div>
                ) : (
                  buckets[col.status].map((lead) => (
                    <LeadCard
                      key={lead.id}
                      lead={lead}
                      draggable={canMutate}
                      onDragStart={(ld) => setDragLead(ld)}
                      onDragEnd={() => {
                        setDragLead(null)
                        setHoverColumn(null)
                      }}
                    />
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>

      {pendingLost && (
        <LostReasonDialog
          loading={setStatus.isPending}
          onConfirm={confirmLost}
          onCancel={() => setPendingLost(null)}
        />
      )}
    </>
  )
}
