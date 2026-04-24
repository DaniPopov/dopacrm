import { useState, type FormEvent } from "react"

export type CoachFormValues = {
  first_name: string
  last_name: string
  phone?: string | null
  email?: string | null
}

/**
 * Shared create/edit form for a Coach.
 *
 * Used by the "Create coach" card on the list page AND the "Edit"
 * dialog on the detail page. Pay/class assignment happens separately
 * via ClassCoachesSection — a coach exists first, then gets linked to
 * classes.
 */
export default function CoachForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Partial<CoachFormValues>
  submitting?: boolean
  error?: string | null
  submitLabel: string
  onSubmit: (values: CoachFormValues) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<CoachFormValues>({
    first_name: initial?.first_name ?? "",
    last_name: initial?.last_name ?? "",
    phone: initial?.phone ?? "",
    email: initial?.email ?? "",
  })

  function set<K extends keyof CoachFormValues>(k: K, v: CoachFormValues[K]) {
    setValues((prev) => ({ ...prev, [k]: v }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit({
      first_name: values.first_name.trim(),
      last_name: values.last_name.trim(),
      phone: values.phone?.trim() || null,
      email: values.email?.trim() || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="שם פרטי *">
          <input
            type="text"
            required
            value={values.first_name}
            onChange={(e) => set("first_name", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="שם משפחה *">
          <input
            type="text"
            required
            value={values.last_name}
            onChange={(e) => set("last_name", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="טלפון">
          <input
            type="tel"
            value={values.phone ?? ""}
            onChange={(e) => set("phone", e.target.value)}
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="אימייל">
          <input
            type="email"
            value={values.email ?? ""}
            onChange={(e) => set("email", e.target.value)}
            dir="ltr"
            className={inputClass}
          />
        </Field>
      </div>

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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  )
}
