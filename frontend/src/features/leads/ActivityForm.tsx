import { useState } from "react"
import { humanizeLeadError } from "@/lib/api-errors"
import { useAddActivity } from "./hooks"
import type { LeadActivityType } from "./types"

const TYPE_OPTIONS: { value: Exclude<LeadActivityType, "status_change">; label: string }[] = [
  { value: "call", label: "📞 שיחה" },
  { value: "email", label: "✉️ מייל" },
  { value: "meeting", label: "🤝 פגישה" },
  { value: "note", label: "📝 הערה" },
]

interface Props {
  leadId: string
}

/**
 * Inline form for adding a touchpoint to the lead's timeline.
 *
 * Type picker excludes ``status_change`` — that's system-only and
 * rejected at the schema layer (422). The user picks one of call /
 * email / meeting / note + types a free-text note.
 */
export function ActivityForm({ leadId }: Props) {
  const [type, setType] = useState<Exclude<LeadActivityType, "status_change">>("call")
  const [note, setNote] = useState("")
  const add = useAddActivity()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!note.trim()) return
    add.mutate(
      { id: leadId, data: { type, note: note.trim() } },
      {
        onSuccess: () => {
          setNote("")
          add.reset()
        },
      },
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm"
    >
      <div className="mb-2 flex flex-wrap gap-1.5">
        {TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setType(opt.value)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              type === opt.value
                ? "border-blue-500 bg-blue-50 text-blue-700"
                : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="הוסיפו הערה — תמליל שיחה, סיכום פגישה, וכו'"
        rows={2}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
      />
      {add.error && (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {humanizeLeadError(add.error)}
        </div>
      )}
      <div className="mt-2 flex justify-end">
        <button
          type="submit"
          disabled={add.isPending || !note.trim()}
          className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {add.isPending ? "שומר..." : "הוסף"}
        </button>
      </div>
    </form>
  )
}
