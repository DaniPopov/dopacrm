import { useNavigate, useParams } from "react-router-dom"
import { humanizeMemberError } from "@/lib/api-errors"
import MemberForm, { type MemberFormValues } from "./MemberForm"
import { useMember, useUpdateMember } from "./hooks"

/**
 * Member edit page — `/members/:id`.
 *
 * Opened from clicking a member's name in the list, or the "עריכה"
 * action. On save, navigates back to `/members`. Fetching happens via
 * TanStack Query; the list cache usually has the member already so
 * this page loads instantly.
 */
export default function MemberDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: member, isLoading, error } = useMember(id ?? "")
  const update = useUpdateMember()

  function handleSubmit(values: MemberFormValues) {
    if (!id) return
    update.mutate(
      { id, data: values },
      {
        onSuccess: () => {
          update.reset()
          navigate("/members")
        },
      },
    )
  }

  function handleCancel() {
    update.reset()
    navigate("/members")
  }

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error || !member) {
    return (
      <div>
        <button
          onClick={() => navigate("/members")}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="py-20 text-center text-red-500">
          {error?.message ?? "המנוי לא נמצא"}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            onClick={() => navigate("/members")}
            className="mb-1 text-sm text-blue-600 hover:underline"
          >
            ← חזרה לרשימה
          </button>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            {member.first_name} {member.last_name}
          </h1>
          <p className="mt-1 text-xs text-gray-400" dir="ltr">
            {member.phone}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <MemberForm
          initial={member}
          submitting={update.isPending}
          error={update.error ? humanizeMemberError(update.error) : null}
          submitLabel="שמור שינויים"
          onSubmit={handleSubmit}
          onCancel={handleCancel}
        />
      </div>
    </div>
  )
}
