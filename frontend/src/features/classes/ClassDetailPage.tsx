import { useNavigate, useParams } from "react-router-dom"
import { humanizeClassError } from "@/lib/api-errors"
import ClassForm, { type ClassFormValues } from "./ClassForm"
import { useClass, useUpdateClass } from "./hooks"

/**
 * Class edit page — `/classes/:id`.
 *
 * Opened from clicking a class name in the list. On save, navigates
 * back to `/classes`. Cancel does the same. Mirrors the pattern used
 * by TenantDetailPage and MemberDetailPage.
 */
export default function ClassDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: cls, isLoading, error } = useClass(id ?? "")
  const update = useUpdateClass()

  function handleSubmit(values: ClassFormValues) {
    if (!id) return
    update.mutate(
      { id, data: values },
      {
        onSuccess: () => {
          update.reset()
          navigate("/classes")
        },
      },
    )
  }

  function handleCancel() {
    update.reset()
    navigate("/classes")
  }

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error || !cls) {
    return (
      <div>
        <button
          onClick={() => navigate("/classes")}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="py-20 text-center text-red-500">
          {error?.message ?? "השיעור לא נמצא"}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            onClick={() => navigate("/classes")}
            className="mb-1 text-sm text-blue-600 hover:underline"
          >
            ← חזרה לרשימה
          </button>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            עריכת {cls.name}
          </h1>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <ClassForm
          initial={cls}
          submitting={update.isPending}
          error={update.error ? humanizeClassError(update.error) : null}
          submitLabel="שמור שינויים"
          onSubmit={handleSubmit}
          onCancel={handleCancel}
        />
      </div>
    </div>
  )
}
