import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { StatusBadge, type StatusVariant } from "@/components/ui/status-badge"
import type { Lead, LeadSource } from "./types"

const SOURCE_LABEL: Record<LeadSource, string> = {
  walk_in: "מזדמן",
  website: "אתר",
  referral: "הפניה",
  social_media: "רשתות",
  ad: "פרסום",
  other: "אחר",
}

const SOURCE_VARIANT: Record<LeadSource, StatusVariant> = {
  walk_in: "primary",
  website: "info",
  referral: "success",
  social_media: "info",
  ad: "warning",
  other: "neutral",
}

interface Props {
  lead: Lead
  draggable?: boolean
  onDragStart?: (lead: Lead, e: React.DragEvent) => void
  onDragEnd?: () => void
}

export function LeadCard({ lead, draggable = true, onDragStart, onDragEnd }: Props) {
  const navigate = useNavigate()

  // Snapshot "now" once at mount via useState lazy init — avoids the
  // React Compiler "impure call during render" lint flag and keeps the
  // age label stable while the card is on screen.
  const [now] = useState(() => Date.now())
  const daysAgo = Math.floor(
    (now - new Date(lead.created_at).getTime()) / (1000 * 60 * 60 * 24),
  )
  const ageLabel =
    daysAgo === 0 ? "היום" : daysAgo === 1 ? "אתמול" : `לפני ${daysAgo} ימים`

  return (
    <div
      draggable={draggable}
      onClick={() => navigate(`/leads/${lead.id}`)}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move"
        e.dataTransfer.setData("text/plain", lead.id)
        onDragStart?.(lead, e)
      }}
      onDragEnd={onDragEnd}
      className="group cursor-pointer rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition-shadow hover:border-blue-300 hover:shadow-md"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-gray-900">
            {lead.first_name} {lead.last_name}
          </div>
          <div className="truncate text-xs text-gray-500" dir="ltr">
            {lead.phone}
          </div>
        </div>
        <StatusBadge variant={SOURCE_VARIANT[lead.source]}>
          {SOURCE_LABEL[lead.source]}
        </StatusBadge>
      </div>
      {lead.notes && (
        <div className="mb-2 line-clamp-2 text-xs text-gray-600">{lead.notes}</div>
      )}
      <div className="text-xs text-gray-400">{ageLabel}</div>
    </div>
  )
}
