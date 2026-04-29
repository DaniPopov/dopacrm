import { useEffect, useRef, useState } from "react"
import { useLostReasons } from "./hooks"

/**
 * Lost-reason capture dialog with autocomplete from the tenant's
 * recently-used reasons. Picking a suggestion fills the input; the user
 * can also type something brand new.
 *
 * Cancel = close without committing. Confirm = passes the (possibly
 * empty) reason back to the parent, which calls the status mutation.
 */
interface Props {
  onConfirm: (reason: string) => void
  onCancel: () => void
  loading?: boolean
}

export function LostReasonDialog({ onConfirm, onCancel, loading }: Props) {
  const [reason, setReason] = useState("")
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { data: suggestions } = useLostReasons({ days: 90, limit: 10 })

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const filtered = (suggestions ?? []).filter((row) =>
    row.reason.toLowerCase().includes(reason.toLowerCase()),
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h2 className="mb-2 text-lg font-bold text-gray-900">סיבת אובדן</h2>
        <p className="mb-4 text-sm text-gray-500">
          מומלץ לציין סיבה — עוזר להבין מה לתקן בתהליך המכירה.
        </p>

        <div className="relative mb-4">
          <input
            ref={inputRef}
            type="text"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value)
              setShowSuggestions(true)
            }}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => {
              // Slight delay so a click on a suggestion lands first.
              setTimeout(() => setShowSuggestions(false), 150)
            }}
            placeholder="למשל: יקר מדי, לא במיקום נוח..."
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
          />
          {showSuggestions && filtered.length > 0 && (
            <div className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg">
              {filtered.map((row) => (
                <button
                  key={row.reason}
                  type="button"
                  onClick={() => {
                    setReason(row.reason)
                    setShowSuggestions(false)
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 text-right text-sm hover:bg-gray-50"
                >
                  <span className="text-gray-900">{row.reason}</span>
                  <span className="text-xs text-gray-400">{row.count}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
          >
            ביטול
          </button>
          <button
            type="button"
            onClick={() => onConfirm(reason.trim())}
            disabled={loading}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          >
            {loading ? "שומר..." : "סימון כאבוד"}
          </button>
        </div>
      </div>
    </div>
  )
}
