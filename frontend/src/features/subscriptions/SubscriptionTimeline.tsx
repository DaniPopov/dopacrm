import type { SubscriptionEvent, SubscriptionEventType } from "./types"

/**
 * Human-readable rendering of a subscription's timeline.
 *
 * Reads the ``subscription_events`` rows and turns each into a Hebrew
 * sentence + a date. The one non-trivial case is ``renewed`` on an
 * expired→active transition: ``event_data.days_late`` is shown as a
 * small pill so the owner can see retention friction at a glance
 * ("Dana חודש 3 ימי איחור").
 */

const EVENT_LABELS: Record<SubscriptionEventType, string> = {
  created: "נפתח מנוי",
  frozen: "המנוי הוקפא",
  unfrozen: "המנוי הופשר",
  expired: "המנוי פג תוקף",
  renewed: "המנוי חודש",
  replaced: "המסלול הוחלף",
  changed_plan: "נפתח מנוי חדש מתוך החלפת מסלול",
  cancelled: "המנוי בוטל",
}

export default function SubscriptionTimeline({
  events,
}: {
  events: SubscriptionEvent[]
}) {
  if (events.length === 0) {
    return <div className="text-sm text-gray-400">אין אירועים</div>
  }

  return (
    <ol className="space-y-2">
      {events.map((e) => (
        <li key={e.id} className="flex items-start gap-3 text-sm">
          <div className="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-blue-500" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-medium text-gray-900">
                {EVENT_LABELS[e.event_type]}
              </span>
              <Pills event={e} />
            </div>
            <div className="text-xs text-gray-400">{formatDate(e.occurred_at)}</div>
            {e.event_data.detail && typeof e.event_data.detail === "string" && (
              <div className="mt-1 text-xs text-gray-500">{e.event_data.detail}</div>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

/* ── Extra pills for events that carry noteworthy payload ─────── */

function Pills({ event }: { event: SubscriptionEvent }) {
  const pills: { label: string; className: string }[] = []

  // Late-renewal pill: the gym-owner signal we built the whole events
  // table for ("how many members renewed late this month?").
  if (
    event.event_type === "renewed" &&
    typeof event.event_data.days_late === "number" &&
    event.event_data.days_late > 0
  ) {
    pills.push({
      label: `${event.event_data.days_late} ימי איחור`,
      className: "border-amber-200 bg-amber-50 text-amber-700",
    })
  }

  // Cancellation reason key → Hebrew label
  if (event.event_type === "cancelled" && typeof event.event_data.reason === "string") {
    const reasonLabel = cancellationReasonLabel(event.event_data.reason)
    if (reasonLabel) {
      pills.push({
        label: reasonLabel,
        className: "border-red-200 bg-red-50 text-red-700",
      })
    }
  }

  // System-triggered events (nightly jobs) — small muted marker
  if (event.created_by === null) {
    pills.push({
      label: "אוטומטי",
      className: "border-gray-200 bg-gray-50 text-gray-500",
    })
  }

  if (pills.length === 0) return null
  return (
    <>
      {pills.map((p, i) => (
        <span
          key={i}
          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${p.className}`}
        >
          {p.label}
        </span>
      ))}
    </>
  )
}

function cancellationReasonLabel(key: string): string | null {
  return (
    {
      moved_away: "עבר דירה",
      too_expensive: "יקר מדי",
      not_using: "לא מנצל",
      injury: "פציעה",
      other: "אחר",
    }[key] ?? null
  )
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("he-IL", {
      day: "numeric",
      month: "long",
      year: "numeric",
    })
  } catch {
    return iso
  }
}
