import { useLeadActivities } from "./hooks"
import type { LeadActivity, LeadActivityType } from "./types"

const TYPE_META: Record<LeadActivityType, { icon: string; label: string; tint: string }> = {
  call: { icon: "📞", label: "שיחה", tint: "border-blue-200 bg-blue-50" },
  email: { icon: "✉️", label: "מייל", tint: "border-indigo-200 bg-indigo-50" },
  meeting: { icon: "🤝", label: "פגישה", tint: "border-amber-200 bg-amber-50" },
  note: { icon: "📝", label: "הערה", tint: "border-gray-200 bg-gray-50" },
  status_change: {
    icon: "🔄",
    label: "שינוי סטטוס",
    tint: "border-violet-200 bg-violet-50",
  },
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const days = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24))
  if (days === 0) {
    const hrs = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60))
    if (hrs === 0) return "עכשיו"
    return `לפני ${hrs} שעות`
  }
  if (days === 1) return "אתמול"
  if (days < 7) return `לפני ${days} ימים`
  return d.toLocaleDateString("he-IL")
}

interface Props {
  leadId: string
}

export function ActivityTimeline({ leadId }: Props) {
  const { data: activities, isLoading } = useLeadActivities(leadId)

  if (isLoading) {
    return <div className="py-8 text-center text-sm text-gray-400">טוען...</div>
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">
        אין פעילות עדיין. הוסיפו את הראשונה למעלה.
      </div>
    )
  }

  return (
    <ol className="space-y-3">
      {activities.map((activity) => (
        <ActivityRow key={activity.id} activity={activity} />
      ))}
    </ol>
  )
}

function ActivityRow({ activity }: { activity: LeadActivity }) {
  const meta = TYPE_META[activity.type]
  return (
    <li className={`rounded-lg border ${meta.tint} p-3`}>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold text-gray-700">
          {meta.icon} {meta.label}
        </span>
        <span className="text-gray-500">{formatTime(activity.created_at)}</span>
      </div>
      <div className="whitespace-pre-wrap text-sm text-gray-900">
        {activity.note}
      </div>
    </li>
  )
}
