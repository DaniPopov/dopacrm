import { useNavigate, useParams } from "react-router-dom"
import { humanizePlanError } from "@/lib/api-errors"
import PlanForm, { type PlanFormValues } from "./PlanForm"
import { usePlan, useUpdatePlan } from "./hooks"

/**
 * Plan edit page — `/plans/:id`.
 *
 * Opened from clicking a plan name in the list. On save, navigates
 * back to `/plans`. Cancel does the same. Mirrors ClassDetailPage.
 *
 * PATCH semantics: when the form submits, we send the FULL
 * entitlements list as `entitlements: [...]`, which tells the backend
 * to REPLACE the rule set atomically.
 */
export default function PlanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: plan, isLoading, error } = usePlan(id ?? "")
  const update = useUpdatePlan()

  function handleSubmit(values: PlanFormValues) {
    if (!id) return
    update.mutate(
      { id, data: values },
      {
        onSuccess: () => {
          update.reset()
          navigate("/plans")
        },
      },
    )
  }

  function handleCancel() {
    update.reset()
    navigate("/plans")
  }

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error || !plan) {
    return (
      <div>
        <button
          onClick={() => navigate("/plans")}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← חזרה לרשימה
        </button>
        <div className="py-20 text-center text-red-500">
          {error?.message ?? "המסלול לא נמצא"}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            onClick={() => navigate("/plans")}
            className="mb-1 text-sm text-blue-600 hover:underline"
          >
            ← חזרה לרשימה
          </button>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            עריכת {plan.name}
          </h1>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <PlanForm
          initial={plan}
          submitting={update.isPending}
          error={update.error ? humanizePlanError(update.error) : null}
          submitLabel="שמור שינויים"
          onSubmit={handleSubmit}
          onCancel={handleCancel}
        />
      </div>
    </div>
  )
}
