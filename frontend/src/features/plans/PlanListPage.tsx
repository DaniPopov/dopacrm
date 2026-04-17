import { useState } from "react"
import { DataTable, useRowClickNavigator } from "@/components/ui/data-table"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { StatusBadge } from "@/components/ui/status-badge"
import { useAuth } from "@/features/auth/auth-provider"
import { useClasses } from "@/features/classes/hooks"
import { humanizePlanError } from "@/lib/api-errors"
import PlanForm, { type PlanFormValues } from "./PlanForm"
import {
  useActivatePlan,
  useCreatePlan,
  useDeactivatePlan,
  usePlans,
} from "./hooks"
import type { MembershipPlan, PlanEntitlement } from "./types"

/**
 * Membership plans list page — `/plans`.
 *
 * Migrated to shared `DataTable` + `PageHeader` + `StatusBadge` + `EmptyState`.
 * The inline create form stays feature-local. Plan-specific formatters
 * (price, billing period, entitlement summary) live below.
 */
export default function PlanListPage() {
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const {
    data: plans,
    isLoading,
    error,
  } = usePlans({ includeInactive: showInactive })
  const { data: classes } = useClasses({ includeInactive: true })
  const create = useCreatePlan()
  const deactivate = useDeactivatePlan()
  const activate = useActivatePlan()

  const canMutate = user?.role === "owner" || user?.role === "super_admin"
  const classNameById = new Map((classes ?? []).map((c) => [c.id, c.name]))
  const openDetail = useRowClickNavigator<MembershipPlan>((p) => `/plans/${p.id}`)

  function handleCreate(values: PlanFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  return (
    <div>
      <PageHeader
        title="מסלולי חברות"
        subtitle="המסלולים שחדר הכושר מציע למנויים"
        action={
          canMutate && !showCreate ? (
            <button
              onClick={() => setShowCreate(true)}
              className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
            >
              + מסלול חדש
            </button>
          ) : undefined
        }
      />

      {showCreate && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50/30 p-6">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">מסלול חדש</h3>
            <button
              onClick={() => {
                setShowCreate(false)
                create.reset()
              }}
              className="text-gray-400 hover:text-gray-600"
              aria-label="סגירה"
            >
              ✕
            </button>
          </div>
          <PlanForm
            submitting={create.isPending}
            error={create.error ? humanizePlanError(create.error) : null}
            submitLabel="צור מסלול"
            onSubmit={handleCreate}
            onCancel={() => {
              setShowCreate(false)
              create.reset()
            }}
          />
        </div>
      )}

      <div className="mb-4 flex items-center gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="rounded border-gray-300"
          />
          הצג מסלולים לא פעילים
        </label>
      </div>

      {!isLoading && !error && (!plans || plans.length === 0) ? (
        <EmptyState
          message={
            showInactive
              ? "אין מסלולים עדיין. הוסיפו את הראשון!"
              : "אין מסלולים פעילים. הוסיפו אחד או הציגו גם לא פעילים."
          }
        />
      ) : (
        <DataTable<MembershipPlan>
          data={plans}
          isLoading={isLoading}
          error={error}
          rowKey={(p) => p.id}
          onRowClick={openDetail}
          columns={[
            {
              header: "שם",
              cell: (p) => (
                <div>
                  <div className="font-medium text-gray-900">{p.name}</div>
                  {p.description && (
                    <div className="mt-0.5 max-w-xs truncate text-xs text-gray-500">
                      {p.description}
                    </div>
                  )}
                </div>
              ),
              primaryMobile: true,
            },
            {
              header: "סוג",
              cell: (p) => (p.type === "recurring" ? "מתחדש" : "חד-פעמי"),
            },
            {
              header: "מחיר",
              cell: (p) => (
                <span className="font-semibold text-gray-900" dir="ltr">
                  {formatPrice(p.price_cents, p.currency)}
                </span>
              ),
            },
            {
              header: "חיוב",
              cell: (p) => (
                <>
                  {formatBillingPeriod(p.billing_period, p.type)}
                  {p.type === "one_time" && p.duration_days != null && (
                    <span className="text-xs text-gray-400"> — {p.duration_days} ימים</span>
                  )}
                </>
              ),
            },
            {
              header: "הרשאות",
              cell: (p) => (
                <EntitlementsSummary
                  entitlements={p.entitlements}
                  classNameById={classNameById}
                  compact
                />
              ),
              className: "max-w-[260px]",
            },
            {
              header: "סטטוס",
              cell: (p) => (
                <StatusBadge variant={p.is_active ? "success" : "neutral"}>
                  {p.is_active ? "פעיל" : "לא פעיל"}
                </StatusBadge>
              ),
            },
          ]}
          rowActions={
            canMutate
              ? [
                  { label: "עריכה", onClick: openDetail },
                  {
                    label: "השבתה",
                    onClick: (p) => deactivate.mutate(p.id),
                    hidden: (p) => !p.is_active,
                  },
                  {
                    label: "הפעלה",
                    onClick: (p) => activate.mutate(p.id),
                    hidden: (p) => p.is_active,
                  },
                ]
              : []
          }
        />
      )}
    </div>
  )
}

/* ── Formatters (plan-specific, stay local) ───────────────── */

function formatPrice(cents: number, currency: string): string {
  const symbol =
    currency === "ILS" ? "₪" : currency === "USD" ? "$" : currency === "EUR" ? "€" : currency
  const amount = (cents / 100).toLocaleString("he-IL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
  return `${symbol}${amount}`
}

function formatBillingPeriod(period: string, type: string): string {
  if (type === "one_time") return "חד-פעמי"
  return { monthly: "חודשי", quarterly: "רבעוני", yearly: "שנתי" }[period] ?? period
}

function formatResetPeriod(reset: string): string {
  return (
    {
      weekly: "שבועי",
      monthly: "חודשי",
      billing_period: "תקופת חיוב",
      never: "סה״כ",
      unlimited: "ללא הגבלה",
    }[reset] ?? reset
  )
}

function summarizeEntitlement(
  e: PlanEntitlement,
  classNameById: Map<string, string>,
): string {
  const className = e.class_id
    ? (classNameById.get(e.class_id) ?? "שיעור נמחק")
    : "כל השיעורים"
  if (e.reset_period === "unlimited") return `${className} — ללא הגבלה`
  const cadence = formatResetPeriod(e.reset_period)
  return `${e.quantity} × ${className} (${cadence})`
}

function EntitlementsSummary({
  entitlements,
  classNameById,
  compact = false,
}: {
  entitlements: PlanEntitlement[]
  classNameById: Map<string, string>
  compact?: boolean
}) {
  if (entitlements.length === 0) {
    return <span className="text-xs text-gray-500">ללא הגבלה</span>
  }
  const lines = entitlements.map((e) => summarizeEntitlement(e, classNameById))
  if (compact && lines.length > 2) {
    return (
      <span className="text-xs text-gray-600">
        {lines.slice(0, 2).join(" • ")}
        <span className="text-gray-400"> +{lines.length - 2}</span>
      </span>
    )
  }
  return (
    <ul className="space-y-0.5 text-xs text-gray-700">
      {lines.map((l, i) => (
        <li key={i}>{l}</li>
      ))}
    </ul>
  )
}
