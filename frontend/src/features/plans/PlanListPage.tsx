import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useDevice } from "@/hooks/useDevice"
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
 * Owner defines the gym's plans here. Staff/sales can read them (they'll
 * need this when Subscriptions lands for enrolling members). Only owner
 * mutates.
 *
 * Layout mirrors Classes: table on desktop, cards on mobile, inline
 * create card, include-inactive toggle.
 */
export default function PlanListPage() {
  const { isMobile } = useDevice()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [showCreate, setShowCreate] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const { data: plans, isLoading, error } = usePlans({
    includeInactive: showInactive,
  })
  const { data: classes } = useClasses({ includeInactive: true })
  const create = useCreatePlan()

  const canMutate = user?.role === "owner" || user?.role === "super_admin"
  const classNameById = new Map((classes ?? []).map((c) => [c.id, c.name]))

  function handleCreate(values: PlanFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        setShowCreate(false)
        create.reset()
      },
    })
  }

  function openDetail(plan: MembershipPlan) {
    navigate(`/plans/${plan.id}`)
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">מסלולי חברות</h1>
          <p className="mt-1 text-sm text-gray-500">
            המסלולים שחדר הכושר מציע למנויים
          </p>
        </div>
        {canMutate && !showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="w-full rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-700 sm:w-auto"
          >
            + מסלול חדש
          </button>
        )}
      </div>

      {/* Create form — inline */}
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

      {/* Include-inactive toggle */}
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

      {/* List */}
      {isLoading ? (
        <div className="py-20 text-center text-gray-400">טוען...</div>
      ) : error ? (
        <div className="py-20 text-center text-red-500">{error.message}</div>
      ) : !plans || plans.length === 0 ? (
        <EmptyState showInactive={showInactive} />
      ) : isMobile ? (
        <div className="space-y-3">
          {plans.map((p) => (
            <PlanCard
              key={p.id}
              plan={p}
              classNameById={classNameById}
              canMutate={canMutate}
              onOpen={() => openDetail(p)}
            />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="rounded-tr-xl px-5 py-3 font-medium text-gray-500">שם</th>
                <th className="px-5 py-3 font-medium text-gray-500">סוג</th>
                <th className="px-5 py-3 font-medium text-gray-500">מחיר</th>
                <th className="px-5 py-3 font-medium text-gray-500">חיוב</th>
                <th className="px-5 py-3 font-medium text-gray-500">הרשאות</th>
                <th className="px-5 py-3 font-medium text-gray-500">סטטוס</th>
                <th className="rounded-tl-xl px-5 py-3 font-medium text-gray-500">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <PlanRow
                  key={p.id}
                  plan={p}
                  classNameById={classNameById}
                  canMutate={canMutate}
                  onOpen={() => openDetail(p)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────── */

function EmptyState({ showInactive }: { showInactive: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-16 text-center text-sm text-gray-400">
      {showInactive
        ? "אין מסלולים עדיין. הוסיפו את הראשון!"
        : "אין מסלולים פעילים. הוסיפו אחד או הציגו גם לא פעילים."}
    </div>
  )
}

/* ── Formatting helpers ──────────────────────────────────── */

function formatPrice(cents: number, currency: string): string {
  const symbol = currency === "ILS" ? "₪" : currency === "USD" ? "$" : currency === "EUR" ? "€" : currency
  const amount = (cents / 100).toLocaleString("he-IL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
  return `${symbol}${amount}`
}

function formatBillingPeriod(period: string, type: string): string {
  if (type === "one_time") return "חד-פעמי"
  return (
    { monthly: "חודשי", quarterly: "רבעוני", yearly: "שנתי" }[period] ?? period
  )
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

/**
 * Short human-readable summary of one entitlement, e.g. "3 יוגה / שבועי"
 * or "ללא הגבלה — ספינינג". Used in the table's "הרשאות" cell.
 */
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

/* ── Status badge ─────────────────────────────────────────── */

function StatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
      פעיל
    </span>
  ) : (
    <span className="inline-flex rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-500">
      לא פעיל
    </span>
  )
}

/* ── Table row ───────────────────────────────────────────── */

function PlanRow({
  plan,
  classNameById,
  canMutate,
  onOpen,
}: {
  plan: MembershipPlan
  classNameById: Map<string, string>
  canMutate: boolean
  onOpen: () => void
}) {
  return (
    <tr className="border-b border-gray-50 transition-colors hover:bg-gray-50/50">
      <td className="px-5 py-3.5">
        <button onClick={onOpen} className="text-right hover:underline">
          <div className="font-medium text-gray-900">{plan.name}</div>
          {plan.description && (
            <div className="mt-0.5 max-w-xs truncate text-xs text-gray-500">
              {plan.description}
            </div>
          )}
        </button>
      </td>
      <td className="px-5 py-3.5 text-gray-700">
        {plan.type === "recurring" ? "מתחדש" : "חד-פעמי"}
      </td>
      <td className="px-5 py-3.5 font-semibold text-gray-900" dir="ltr">
        {formatPrice(plan.price_cents, plan.currency)}
      </td>
      <td className="px-5 py-3.5 text-gray-700">
        {formatBillingPeriod(plan.billing_period, plan.type)}
        {plan.type === "one_time" && plan.duration_days != null && (
          <span className="text-xs text-gray-400"> — {plan.duration_days} ימים</span>
        )}
      </td>
      <td className="max-w-[260px] px-5 py-3.5">
        <EntitlementsSummary
          entitlements={plan.entitlements}
          classNameById={classNameById}
          compact
        />
      </td>
      <td className="px-5 py-3.5">
        <StatusBadge isActive={plan.is_active} />
      </td>
      <td className="px-5 py-3.5">
        <PlanActions plan={plan} canMutate={canMutate} onEdit={onOpen} />
      </td>
    </tr>
  )
}

/* ── Mobile card ─────────────────────────────────────────── */

function PlanCard({
  plan,
  classNameById,
  canMutate,
  onOpen,
}: {
  plan: MembershipPlan
  classNameById: Map<string, string>
  canMutate: boolean
  onOpen: () => void
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <button onClick={onOpen} className="min-w-0 flex-1 text-right">
          <div className="truncate font-semibold text-gray-900">{plan.name}</div>
          {plan.description && (
            <div className="mt-0.5 truncate text-xs text-gray-500">
              {plan.description}
            </div>
          )}
        </button>
        <StatusBadge isActive={plan.is_active} />
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-lg font-bold text-gray-900" dir="ltr">
          {formatPrice(plan.price_cents, plan.currency)}
        </span>
        <span className="text-xs text-gray-500">
          {formatBillingPeriod(plan.billing_period, plan.type)}
          {plan.type === "one_time" && plan.duration_days != null &&
            ` — ${plan.duration_days} ימים`}
        </span>
      </div>

      <div className="mt-3 border-t border-gray-100 pt-3">
        <div className="mb-1 text-xs font-medium text-gray-500">הרשאות</div>
        <EntitlementsSummary
          entitlements={plan.entitlements}
          classNameById={classNameById}
        />
      </div>

      <div className="mt-3 border-t border-gray-100 pt-3">
        <PlanActions plan={plan} canMutate={canMutate} onEdit={onOpen} />
      </div>
    </div>
  )
}

/* ── Actions dropdown ────────────────────────────────────── */

function PlanActions({
  plan,
  canMutate,
  onEdit,
}: {
  plan: MembershipPlan
  canMutate: boolean
  onEdit: () => void
}) {
  const deactivate = useDeactivatePlan()
  const activate = useActivatePlan()
  const [menuOpen, setMenuOpen] = useState(false)

  const isBusy = deactivate.isPending || activate.isPending

  if (!canMutate) {
    return <span className="text-xs text-gray-400">צפייה בלבד</span>
  }

  function doAction(fn: () => void) {
    setMenuOpen(false)
    fn()
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMenuOpen((v) => !v)}
        disabled={isBusy}
        className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50 sm:w-auto"
      >
        {isBusy ? "..." : "פעולות ▾"}
      </button>
      {menuOpen && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 min-w-[140px] rounded-lg border border-gray-200 bg-white py-1 text-right shadow-lg sm:right-auto">
          <MenuItem label="עריכה" onClick={() => doAction(onEdit)} />
          {plan.is_active ? (
            <MenuItem
              label="השבתה"
              onClick={() => doAction(() => deactivate.mutate(plan.id))}
            />
          ) : (
            <MenuItem
              label="הפעלה"
              onClick={() => doAction(() => activate.mutate(plan.id))}
            />
          )}
        </div>
      )}
    </div>
  )
}

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="block w-full px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
    >
      {label}
    </button>
  )
}
