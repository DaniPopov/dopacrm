import { useState } from "react"
import CreateUserForm from "@/features/users/CreateUserForm"
import { useTenantUsers } from "@/features/users/hooks"
import type { User } from "@/features/users/types"

const ROLE_LABELS: Record<string, string> = {
  super_admin: "מנהל על",
  owner: "בעלים",
  staff: "צוות",
  sales: "מכירות",
}

/**
 * Users management section inside the tenant detail page.
 * Shows the list of gym staff and opens an inline create form.
 */
export default function TenantUsersSection({ tenantId }: { tenantId: string }) {
  const { data: users, isLoading, error } = useTenantUsers(tenantId)
  const [creating, setCreating] = useState(false)

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">משתמשים</h2>
          <p className="text-sm text-gray-500">צוות חדר הכושר שיכול להיכנס למערכת</p>
        </div>
        {!creating && (
          <button
            onClick={() => setCreating(true)}
            className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700"
          >
            + הוסף משתמש
          </button>
        )}
      </div>

      {creating && (
        <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-base font-bold text-gray-900">משתמש חדש</h3>
            <button
              onClick={() => setCreating(false)}
              className="text-gray-400 hover:text-gray-600"
              aria-label="סגור"
            >
              ✕
            </button>
          </div>
          <CreateUserForm
            tenantId={tenantId}
            onCreated={() => setCreating(false)}
            onCancel={() => setCreating(false)}
          />
        </div>
      )}

      {isLoading ? (
        <div className="py-8 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="py-8 text-center text-red-500">{(error as Error).message}</div>
      ) : !users || users.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-10 text-center text-sm text-gray-400">
          אין משתמשים עדיין. הוסיפו את הראשון!
        </div>
      ) : (
        <div className="space-y-2">
          {users.map((u) => (
            <UserRow key={u.id} user={u} />
          ))}
        </div>
      )}
    </section>
  )
}

function UserRow({ user }: { user: User }) {
  const displayName =
    [user.first_name, user.last_name].filter(Boolean).join(" ") || user.email.split("@")[0]

  return (
    <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-sm font-semibold text-white">
        {initialOf(user)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-gray-900">{displayName}</div>
        <div className="truncate text-xs text-gray-500">{user.email}</div>
      </div>
      <span className="rounded-full border border-gray-200 px-2.5 py-0.5 text-xs font-medium text-gray-600">
        {ROLE_LABELS[user.role] ?? user.role}
      </span>
      {!user.is_active && (
        <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 text-xs text-red-700">
          לא פעיל
        </span>
      )}
    </div>
  )
}

function initialOf(user: User): string {
  const first = user.first_name?.charAt(0) ?? ""
  const last = user.last_name?.charAt(0) ?? ""
  if (first || last) return (first + last).toUpperCase() || "?"
  return (user.email.charAt(0) || "?").toUpperCase()
}
