import { useState, type FormEvent } from "react"

/**
 * "At quota / not covered — allow anyway?" modal.
 *
 * The server already rejected the entry with either QUOTA_EXCEEDED or
 * CLASS_NOT_COVERED. Staff confirms the override here, optionally adds
 * a reason, and the parent retries the POST with override=true + this
 * reason (the entry gets ``override=true`` + the right ``override_kind``
 * for owner audit).
 */
export default function QuotaOverrideDialog({
  kind,
  className,
  onConfirm,
  onCancel,
  submitting,
}: {
  kind: "quota_exceeded" | "not_covered"
  /** The class name (for the Hebrew copy). */
  className: string
  submitting?: boolean
  onConfirm: (reason: string | null) => void
  onCancel: () => void
}) {
  const [reason, setReason] = useState("")

  const title = kind === "quota_exceeded" ? "המנוי במכסה מלאה" : "שיעור לא כלול במסלול"
  const body =
    kind === "quota_exceeded"
      ? `המנוי ניצל את כל המכסה שלו לתקופה עבור ${className}. לאשר כניסה בכל זאת?`
      : `${className} לא כלול במסלול של המנוי. לאשר כניסה בכל זאת?`

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onConfirm(reason.trim() || null)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="text-lg font-bold text-amber-700">{title}</h3>
          <button
            type="button"
            onClick={onCancel}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            ✕
          </button>
        </div>
        <p className="text-sm text-gray-700">{body}</p>
        <label className="mt-4 block">
          <span className="mb-1 block text-sm font-medium text-gray-700">
            סיבה (אופציונלי)
          </span>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            placeholder="למשל: שיעור יום הולדת"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
          />
        </label>
        <div className="mt-6 flex justify-end gap-3 border-t border-gray-100 pt-4">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            ביטול
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-amber-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
          >
            {submitting ? "שומר..." : "אשר כניסה"}
          </button>
        </div>
      </form>
    </div>
  )
}
