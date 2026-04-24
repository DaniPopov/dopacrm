import { useState, type FormEvent } from "react"
import PasswordInput from "@/components/ui/password-input"
import { humanizeUserError } from "@/lib/api-errors"
import { useUpdateUser } from "./hooks"
import type { Role, UpdateUserRequest, User } from "./types"

/**
 * Modal dialog for editing a user.
 *
 * Opens from the "עריכה" row action in TenantUsersSection. Prefills
 * all fields from the provided user, lets super_admin change any of:
 * first_name, last_name, email, phone, role, is_active, and password.
 *
 * Password field is optional — leaving it blank keeps the existing
 * hash untouched. Only fields the user actually edited are sent (the
 * form does a shallow diff vs the initial values) so untouched fields
 * don't accidentally wipe themselves.
 */
export default function EditUserDialog({
  user,
  tenantId,
  onClose,
}: {
  /** User being edited — fields prefill from this. */
  user: User
  /** Owning tenant, used for query invalidation. */
  tenantId: string
  /** Close the dialog (called after save or on cancel). */
  onClose: () => void
}) {
  const update = useUpdateUser(tenantId)
  const [form, setForm] = useState({
    first_name: user.first_name ?? "",
    last_name: user.last_name ?? "",
    email: user.email,
    phone: user.phone ?? "",
    role: user.role,
    is_active: user.is_active,
    password: "", // blank = no change
  })

  /** Update a single field immutably. */
  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // Build a patch with only changed fields — empty password is dropped
    const patch: UpdateUserRequest = {}
    if (form.first_name !== (user.first_name ?? "")) patch.first_name = form.first_name || null
    if (form.last_name !== (user.last_name ?? "")) patch.last_name = form.last_name || null
    if (form.email !== user.email) patch.email = form.email
    if (form.phone !== (user.phone ?? "")) patch.phone = form.phone || null
    if (form.role !== user.role) patch.role = form.role
    if (form.is_active !== user.is_active) patch.is_active = form.is_active
    if (form.password.length > 0) patch.password = form.password

    // Nothing to patch → just close
    if (Object.keys(patch).length === 0) {
      onClose()
      return
    }

    update.mutate(
      { id: user.id, data: patch },
      {
        onSuccess: () => {
          update.reset()
          onClose()
        },
      },
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="my-8 w-full max-w-2xl rounded-xl bg-white p-6 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">עריכת משתמש</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="שם פרטי">
              <input
                type="text"
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
                className={inputClass}
              />
            </Field>
            <Field label="שם משפחה">
              <input
                type="text"
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
                className={inputClass}
              />
            </Field>
            <Field label="אימייל *">
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                dir="ltr"
                className={inputClass}
              />
            </Field>
            <Field label="טלפון">
              <input
                type="tel"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                dir="ltr"
                className={inputClass}
              />
            </Field>
            <Field label="תפקיד">
              <select
                value={form.role}
                onChange={(e) => set("role", e.target.value as Role)}
                className={inputClass}
              >
                <option value="owner">בעלים</option>
                <option value="staff">צוות</option>
                <option value="sales">מכירות</option>
              </select>
            </Field>
            <Field label="סטטוס">
              <select
                value={form.is_active ? "active" : "disabled"}
                onChange={(e) => set("is_active", e.target.value === "active")}
                className={inputClass}
              >
                <option value="active">פעיל</option>
                <option value="disabled">מושבת</option>
              </select>
            </Field>
            <Field
              label="איפוס סיסמה"
              helper="השאירו ריק לשמירת הסיסמה הנוכחית. מינימום 8 תווים"
              className="sm:col-span-2"
            >
              <PasswordInput
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
                placeholder="(ללא שינוי)"
                minLength={form.password.length > 0 ? 8 : undefined}
                dir="ltr"
                className={inputClass}
              />
            </Field>
          </div>

          {update.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
              {humanizeUserError(update.error)}
            </div>
          )}

          <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              ביטול
            </button>
            <button
              type="submit"
              disabled={update.isPending}
              className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {update.isPending ? "שומר..." : "שמור שינויים"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

/** Label + input wrapper with an optional helper line beneath. */
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
