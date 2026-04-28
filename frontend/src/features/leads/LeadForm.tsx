import { useState } from "react"
import type { CreateLeadRequest, Lead, LeadSource } from "./types"

const SOURCE_OPTIONS: { value: LeadSource; label: string }[] = [
  { value: "walk_in", label: "מזדמן (Walk-in)" },
  { value: "website", label: "אתר" },
  { value: "referral", label: "הפניה" },
  { value: "social_media", label: "רשתות חברתיות" },
  { value: "ad", label: "פרסום בתשלום" },
  { value: "other", label: "אחר" },
]

export type LeadFormValues = CreateLeadRequest

interface Props {
  initial?: Lead | null
  submitting: boolean
  error: string | null
  submitLabel: string
  onSubmit: (values: LeadFormValues) => void
  onCancel: () => void
}

export default function LeadForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: Props) {
  const [firstName, setFirstName] = useState(initial?.first_name ?? "")
  const [lastName, setLastName] = useState(initial?.last_name ?? "")
  const [phone, setPhone] = useState(initial?.phone ?? "")
  const [email, setEmail] = useState(initial?.email ?? "")
  const [source, setSource] = useState<LeadSource>(initial?.source ?? "walk_in")
  const [notes, setNotes] = useState(initial?.notes ?? "")

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      phone: phone.trim(),
      email: email.trim() || null,
      source,
      notes: notes.trim() || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            שם פרטי <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            required
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            שם משפחה <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            required
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            טלפון <span className="text-red-500">*</span>
          </label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
            dir="ltr"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            אימייל
          </label>
          <input
            type="email"
            value={email ?? ""}
            onChange={(e) => setEmail(e.target.value)}
            dir="ltr"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">מקור</label>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as LeadSource)}
          className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        >
          {SOURCE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">הערות</label>
        <textarea
          value={notes ?? ""}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        />
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          ביטול
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "שומר..." : submitLabel}
        </button>
      </div>
    </form>
  )
}
