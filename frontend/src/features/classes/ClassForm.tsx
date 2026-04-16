import { useState, type FormEvent } from "react"
import type { CreateGymClassRequest, GymClass } from "./types"

export interface ClassFormValues extends CreateGymClassRequest {}

/**
 * Shared create/edit form for a gym class type.
 *
 * Fields:
 * - name (required, unique within tenant)
 * - description (optional textarea)
 * - color (optional hex, free text — no validation)
 *
 * Used by both the inline create card on the list page and the
 * standalone edit page.
 */
export default function ClassForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  /** Values to prefill in edit mode; omit for create. */
  initial?: Partial<GymClass>
  /** True while the mutation is in flight. */
  submitting?: boolean
  /** Hebrew user-facing error to show above the buttons. */
  error?: string | null
  /** Primary action button text (e.g. "צור שיעור" / "שמור שינויים"). */
  submitLabel: string
  /** Called with the form values on submit. */
  onSubmit: (values: ClassFormValues) => void
  /** Called when the user clicks the cancel button. */
  onCancel: () => void
}) {
  const [form, setForm] = useState<ClassFormValues>({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    color: initial?.color ?? "",
  })

  function set<K extends keyof ClassFormValues>(
    key: K,
    value: ClassFormValues[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit({
      name: form.name,
      description: form.description || null,
      color: form.color || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Field label="שם השיעור *">
        <input
          type="text"
          required
          maxLength={100}
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="ספינינג"
          className={inputClass}
        />
      </Field>

      <Field label="תיאור">
        <textarea
          rows={3}
          value={form.description ?? ""}
          onChange={(e) => set("description", e.target.value)}
          placeholder="שיעור רכיבה עצים בפנים"
          className={`${inputClass} resize-y`}
        />
      </Field>

      <Field label="צבע" helper="קוד HEX מומלץ (למשל #3B82F6)">
        <div className="flex items-center gap-3">
          <input
            type="text"
            maxLength={20}
            value={form.color ?? ""}
            onChange={(e) => set("color", e.target.value)}
            placeholder="#3B82F6"
            dir="ltr"
            className={inputClass}
          />
          {form.color && (
            <div
              className="h-10 w-10 flex-shrink-0 rounded-lg border border-gray-200"
              style={{ backgroundColor: form.color }}
              aria-hidden="true"
            />
          )}
        </div>
      </Field>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
        >
          ביטול
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "שומר..." : submitLabel}
        </button>
      </div>
    </form>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

/** Label + optional helper + input wrapper. */
function Field({
  label,
  helper,
  children,
}: {
  label: string
  helper?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
      {helper && <p className="mt-1 text-xs text-gray-400">{helper}</p>}
    </div>
  )
}
