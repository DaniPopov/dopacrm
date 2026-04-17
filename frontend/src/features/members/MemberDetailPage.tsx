import { useNavigate, useParams } from "react-router-dom"
import { humanizeMemberError } from "@/lib/api-errors"
import MemberQrButton from "@/features/attendance/MemberQrButton"
import MemberSubscriptionSection from "@/features/subscriptions/MemberSubscriptionSection"
import MemberForm, { type MemberFormValues } from "./MemberForm"
import { useMember, useUpdateMember } from "./hooks"

/**
 * Member detail page — `/members/:id`.
 *
 * Two sections:
 * 1. Identity form (name, phone, DOB, notes, etc). Edit + save.
 * 2. Subscription section (current sub card + timeline + history).
 *    The sub section owns all commercial actions: enroll / freeze /
 *    renew / change-plan / cancel.
 *
 * Fetching happens via TanStack Query; list cache usually has the
 * member already so the page loads instantly.
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
          // Stay on the detail page after save so staff can continue
          // with the subscription section below. Previously we navigated
          // away to /members on save, which was jarring when editing a
          // member right before enrolling them.
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
        <MemberQrButton
          memberId={member.id}
          memberName={`${member.first_name} ${member.last_name}`}
        />
      </div>

      <div className="space-y-8">
        {/* Identity form */}
        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">פרטי חבר</h2>
          <MemberForm
            initial={member}
            submitting={update.isPending}
            error={update.error ? humanizeMemberError(update.error) : null}
            submitLabel="שמור שינויים"
            onSubmit={handleSubmit}
            onCancel={handleCancel}
          />
        </section>

        {/* Subscriptions — current + timeline + history + actions */}
        <MemberSubscriptionSection memberId={member.id} />
      </div>
    </div>
  )
}
