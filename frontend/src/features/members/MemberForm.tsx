import { useState, type FormEvent } from "react"
import type { CreateMemberRequest, Member } from "./types"

export interface MemberFormValues extends CreateMemberRequest {}

interface MemberFormProps {
  /** Initial values for edit mode; omit for create. */
  initial?: Partial<Member>
  /** True while the mutation is in flight — disables the submit button. */
  submitting?: boolean
  /** User-facing Hebrew error to show above the action buttons. */
  error?: string | null
  /** Text for the primary action button (e.g. "צור מנוי" / "שמור שינויים"). */
  submitLabel: string
  /** Called with the form values on submit. */
  onSubmit: (values: MemberFormValues) => void
  /** Called when the user clicks cancel. */
  onCancel: () => void
}

/**
 * Shared create/edit form for a member.
 *
 * Required fields: first_name, last_name, phone. Everything else
 * (email, DOB, gender, notes) is optional. `custom_fields` is not
 * edited here in v1 — it's stored/returned unchanged by the API
 * but no UI yet (see docs/features/members.md).
 *
 * Kept in a single file so the create-card and the detail page can
 * both use it without prop drilling.
 */
export default function MemberForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: MemberFormProps) {
  const [form, setForm] = useState<MemberFormValues>({
    first_name: initial?.first_name ?? "",
    last_name: initial?.last_name ?? "",
    phone: initial?.phone ?? "",
    email: initial?.email ?? "",
    date_of_birth: initial?.date_of_birth ?? null,
    gender: initial?.gender ?? "",
    join_date: initial?.join_date ?? null,
    notes: initial?.notes ?? "",
    custom_fields: initial?.custom_fields ?? {},
  })

  /** Update one field immutably. */
  function setField<K extends keyof MemberFormValues>(
    key: K,
    value: MemberFormValues[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ── Section: identity ─────────────────────────────────── */}
      <Section title="פרטים אישיים">
        <Field label="שם פרטי *">
          <input
            type="text"
            required
            value={form.first_name}
            onChange={(e) => setField("first_name", e.target.value)}
            placeholder="דנה"
            className={inputClass}
          />
        </Field>
        <Field label="שם משפחה *">
          <input
            type="text"
            required
            value={form.last_name}
            onChange={(e) => setField("last_name", e.target.value)}
            placeholder="כהן"
            className={inputClass}
          />
        </Field>
        <Field label="מגדר">
          <select
            value={form.gender ?? ""}
            onChange={(e) => setField("gender", e.target.value || null)}
            className={inputClass}
          >
            <option value="">—</option>
            <option value="female">נקבה</option>
            <option value="male">זכר</option>
            <option value="other">אחר</option>
          </select>
        </Field>
        <Field label="תאריך לידה">
          <input
            type="date"
            value={form.date_of_birth ?? ""}
            onChange={(e) => setField("date_of_birth", e.target.value || null)}
            dir="ltr"
            className={inputClass}
          />
        </Field>
      </Section>

      {/* ── Section: contact ──────────────────────────────────── */}
      <Section title="יצירת קשר">
        <Field label="טלפון *" helper="ייחודי לחדר כושר זה">
          <input
            type="tel"
            required
            value={form.phone}
            onChange={(e) => setField("phone", e.target.value)}
            placeholder="+972-50-123-4567"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="אימייל">
          <input
            type="email"
            value={form.email ?? ""}
            onChange={(e) => setField("email", e.target.value || null)}
            placeholder="member@example.com"
            dir="ltr"
            className={inputClass}
          />
        </Field>
      </Section>

      {/* ── Section: membership ───────────────────────────────── */}
      <Section title="חברות">
        <Field label="תאריך הצטרפות" helper="אם לא נמלא — היום">
          <input
            type="date"
            value={form.join_date ?? ""}
            onChange={(e) => setField("join_date", e.target.value || null)}
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="הערות" className="sm:col-span-2">
          <textarea
            rows={3}
            value={form.notes ?? ""}
            onChange={(e) => setField("notes", e.target.value || null)}
            placeholder="פצעים, העדפות, כל דבר שחשוב לזכור"
            className={`${inputClass} resize-y`}
          />
        </Field>
      </Section>

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

/**
 * A titled group of fields in the form.
 * Renders a 2-column grid on tablet+, stacked on mobile.
 */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-3 text-sm font-semibold text-gray-700">{title}</h4>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </div>
  )
}

/**
 * Label + input wrapper with an optional helper line beneath.
 * Pass `className="sm:col-span-2"` to span the full row.
 */
function Field({
  label,
  helper,
  className,
  children,
}: {
  label: string
  helper?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={className}>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
      {helper && <p className="mt-1 text-xs text-gray-400">{helper}</p>}
    </div>
  )
}
