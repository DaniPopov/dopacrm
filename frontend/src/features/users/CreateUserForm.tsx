import { useState, type FormEvent } from "react"
import PasswordInput from "@/components/ui/password-input"
import { ALL_GYM_ROLES, GYM_ROLE_LABELS } from "@/features/auth/types"
import { humanizeUserError } from "@/lib/api-errors"
import { useCreateUser } from "./hooks"
import type { Role } from "./types"

/**
 * Inline form for adding a user to a specific tenant.
 *
 * Used inside the Tenant detail page's Users section. Shown as an
 * expandable card — the outer section controls open/closed state.
 */
export default function CreateUserForm({
  tenantId,
  onCreated,
  onCancel,
}: {
  tenantId: string
  onCreated: () => void
  onCancel: () => void
}) {
  const create = useCreateUser(tenantId)
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    password: "",
    role: "staff" as Role,
  })

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    create.mutate(
      {
        email: form.email,
        password: form.password || null,
        role: form.role,
        tenant_id: tenantId,
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        phone: form.phone || null,
      },
      {
        onSuccess: () => {
          create.reset()
          onCreated()
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="שם פרטי">
          <input
            type="text"
            value={form.first_name}
            onChange={(e) => set("first_name", e.target.value)}
            placeholder="דנה"
            className={inputClass}
          />
        </Field>
        <Field label="שם משפחה">
          <input
            type="text"
            value={form.last_name}
            onChange={(e) => set("last_name", e.target.value)}
            placeholder="כהן"
            className={inputClass}
          />
        </Field>
        <Field label="אימייל *">
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            placeholder="staff@gym.com"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="טלפון">
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => set("phone", e.target.value)}
            placeholder="+972-50-123-4567"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="סיסמה *" helper="מינימום 8 תווים">
          <PasswordInput
            required
            minLength={8}
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="תפקיד *">
          <select
            value={form.role}
            onChange={(e) => set("role", e.target.value as Role)}
            className={inputClass}
          >
            {ALL_GYM_ROLES.map((r) => (
              <option key={r} value={r}>
                {GYM_ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {create.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {humanizeUserError(create.error)}
        </div>
      )}

      <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
        <button
          type="button"
          onClick={() => {
            create.reset()
            onCancel()
          }}
          className="rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
        >
          ביטול
        </button>
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {create.isPending ? "שומר..." : "הוסף משתמש"}
        </button>
      </div>
    </form>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

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
