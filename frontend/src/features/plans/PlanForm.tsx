import { useState, type FormEvent } from "react"
import { useClasses } from "@/features/classes/hooks"
import type {
  BillingPeriod,
  CreatePlanRequest,
  MembershipPlan,
  PlanEntitlementInput,
  PlanType,
  ResetPeriod,
} from "./types"

export interface PlanFormValues extends CreatePlanRequest {}

/**
 * Shared create/edit form for a membership plan + its entitlements.
 *
 * Structure:
 * 1. Header fields — name, description, type, price, billing_period,
 *    duration_days (one_time only), currency
 * 2. Entitlements builder — dynamic list. Zero rows = unlimited any-class
 *    (the default). Each row picks class (or "any"), quantity, and
 *    reset cadence.
 *
 * Shape rules (matching backend):
 * - recurring plan: duration_days must be empty; billing_period ≠ one_time
 * - one_time plan: duration_days required; billing_period = one_time
 * - entitlement with reset="unlimited": quantity must be empty
 * - entitlement with reset≠"unlimited": quantity required, > 0
 *
 * We still let the user type any combo — the backend is the authority.
 * We just show a soft inline hint if they combine invalid options.
 */
export default function PlanForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  /** Values to prefill in edit mode; omit for create. */
  initial?: Partial<MembershipPlan>
  /** True while the mutation is in flight. */
  submitting?: boolean
  /** Hebrew user-facing error to show above the buttons. */
  error?: string | null
  /** Primary action button text. */
  submitLabel: string
  /** Called with the form values on submit. */
  onSubmit: (values: PlanFormValues) => void
  /** Called when the user clicks the cancel button. */
  onCancel: () => void
}) {
  const [form, setForm] = useState<PlanFormValues>(() => ({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    type: (initial?.type as PlanType) ?? "recurring",
    price_cents: initial?.price_cents ?? 0,
    currency: initial?.currency ?? "ILS",
    billing_period: (initial?.billing_period as BillingPeriod) ?? "monthly",
    duration_days: initial?.duration_days ?? null,
    custom_attrs: initial?.custom_attrs ?? {},
    entitlements: (initial?.entitlements ?? []).map((e) => ({
      class_id: e.class_id,
      quantity: e.quantity,
      reset_period: e.reset_period as ResetPeriod,
    })),
  }))

  // Price is held in שקלים for display, converted to אגורות on submit.
  const [priceShekels, setPriceShekels] = useState<string>(
    initial?.price_cents != null ? String(initial.price_cents / 100) : "",
  )

  function set<K extends keyof PlanFormValues>(key: K, value: PlanFormValues[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  // When the user flips to one_time, auto-switch billing_period and clear
  // incompatible fields. Same for the reverse direction — makes the form
  // less fiddly.
  function setType(newType: PlanType) {
    setForm((prev) => ({
      ...prev,
      type: newType,
      billing_period: newType === "one_time" ? "one_time" : "monthly",
      duration_days: newType === "one_time" ? (prev.duration_days ?? 30) : null,
    }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const shekels = Number(priceShekels)
    const priceAgorot = Number.isFinite(shekels) ? Math.round(shekels * 100) : 0
    onSubmit({
      name: form.name.trim(),
      description: form.description?.trim() || null,
      type: form.type,
      price_cents: priceAgorot,
      currency: form.currency || "ILS",
      billing_period: form.billing_period,
      duration_days: form.type === "one_time" ? form.duration_days ?? null : null,
      custom_attrs: form.custom_attrs ?? {},
      entitlements: form.entitlements,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ── Section: basics ─────────────────────────────────── */}
      <Section title="פרטי המסלול">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="שם המסלול *">
            <input
              type="text"
              required
              maxLength={100}
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="חודשי — 3 קבוצתי + 1 אישי"
              className={inputClass}
            />
          </Field>

          <Field label="מטבע">
            <select
              value={form.currency ?? "ILS"}
              onChange={(e) => set("currency", e.target.value)}
              className={inputClass}
            >
              <option value="ILS">₪ שקל</option>
              <option value="USD">$ דולר</option>
              <option value="EUR">€ אירו</option>
            </select>
          </Field>
        </div>

        <Field label="תיאור">
          <textarea
            rows={2}
            value={form.description ?? ""}
            onChange={(e) => set("description", e.target.value)}
            placeholder="3 שיעורים קבוצתיים + אימון אישי אחד בשבוע"
            className={`${inputClass} resize-y`}
          />
        </Field>
      </Section>

      {/* ── Section: pricing + billing ──────────────────────── */}
      <Section title="תמחור וחיוב">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field label="סוג *" helper="מנוי מתחדש או תשלום חד-פעמי">
            <select
              value={form.type}
              onChange={(e) => setType(e.target.value as PlanType)}
              className={inputClass}
            >
              <option value="recurring">מתחדש</option>
              <option value="one_time">חד-פעמי</option>
            </select>
          </Field>

          <Field label={`מחיר (${form.currency === "ILS" ? "₪" : form.currency}) *`}>
            <input
              type="number"
              required
              min={0}
              step={0.01}
              value={priceShekels}
              onChange={(e) => setPriceShekels(e.target.value)}
              placeholder="450"
              className={inputClass}
            />
          </Field>

          {form.type === "recurring" ? (
            <Field label="תדירות חיוב *">
              <select
                value={form.billing_period}
                onChange={(e) => set("billing_period", e.target.value as BillingPeriod)}
                className={inputClass}
              >
                <option value="monthly">חודשי</option>
                <option value="quarterly">רבעוני</option>
                <option value="yearly">שנתי</option>
              </select>
            </Field>
          ) : (
            <Field label="תוקף (בימים) *" helper="מספר הימים שהמסלול תקף">
              <input
                type="number"
                required
                min={1}
                value={form.duration_days ?? ""}
                onChange={(e) =>
                  set(
                    "duration_days",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="30"
                className={inputClass}
              />
            </Field>
          )}
        </div>
      </Section>

      {/* ── Section: entitlements ───────────────────────────── */}
      <EntitlementsBuilder
        value={form.entitlements}
        onChange={(next) => set("entitlements", next)}
      />

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
        >
          ביטול
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "שומר..." : submitLabel}
        </button>
      </div>
    </form>
  )
}

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

/* ── Layout primitives ──────────────────────────────────── */

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <h3 className="border-b border-gray-100 pb-1.5 text-sm font-semibold text-gray-700">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

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

/* ── Entitlements builder ──────────────────────────────────

   Empty list = "unlimited any class" (the backend default). Each row
   narrows access: pick a class (or leave "any"), a quota, and a reset
   cadence. Picking reset="unlimited" hides the quantity input (it must
   be null).

   Classes dropdown comes from useClasses — filtered to active only so
   owners don't accidentally reference a deactivated class.
──────────────────────────────────────────────────────────── */

const RESET_PERIODS: { value: ResetPeriod; label: string; helper: string }[] = [
  { value: "weekly", label: "שבועי", helper: "מתאפס בכל תחילת שבוע" },
  { value: "monthly", label: "חודשי", helper: "מתאפס בתחילת כל חודש" },
  {
    value: "billing_period",
    label: "לכל תקופת חיוב",
    helper: "מתאפס עם כל חידוש של המסלול",
  },
  { value: "never", label: "סה״כ במסלול", helper: "ללא איפוס" },
  { value: "unlimited", label: "ללא הגבלה", helper: "ללא כמות מקסימלית" },
]

function EntitlementsBuilder({
  value,
  onChange,
}: {
  value: PlanEntitlementInput[]
  onChange: (next: PlanEntitlementInput[]) => void
}) {
  const { data: classes } = useClasses()

  function updateRow(idx: number, patch: Partial<PlanEntitlementInput>) {
    onChange(value.map((row, i) => (i === idx ? { ...row, ...patch } : row)))
  }

  function addRow() {
    onChange([
      ...value,
      { class_id: null, quantity: 1, reset_period: "weekly" as ResetPeriod },
    ])
  }

  function removeRow(idx: number) {
    onChange(value.filter((_, i) => i !== idx))
  }

  return (
    <Section title="הרשאות כניסה">
      <p className="text-xs text-gray-500">
        מה המסלול מעניק לחבר? השאירו ריק למסלול ללא הגבלה, או הוסיפו שורות
        כדי להגביל לפי סוג שיעור.
      </p>

      {value.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/50 px-4 py-6 text-center text-sm text-gray-500">
          ללא הגבלה — המנויים יכולים להיכנס לכל שיעור ללא מכסה
        </div>
      ) : (
        <div className="space-y-3">
          {value.map((row, idx) => (
            <EntitlementRow
              key={idx}
              row={row}
              classes={classes ?? []}
              onChange={(patch) => updateRow(idx, patch)}
              onRemove={() => removeRow(idx)}
            />
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={addRow}
        className="rounded-lg border border-dashed border-blue-300 bg-blue-50/30 px-4 py-2 text-sm font-medium text-blue-700 transition-colors hover:border-blue-400 hover:bg-blue-50"
      >
        + הוסף הרשאה
      </button>
    </Section>
  )
}

function EntitlementRow({
  row,
  classes,
  onChange,
  onRemove,
}: {
  row: PlanEntitlementInput
  classes: { id: string; name: string; is_active: boolean }[]
  onChange: (patch: Partial<PlanEntitlementInput>) => void
  onRemove: () => void
}) {
  const isUnlimited = row.reset_period === "unlimited"

  function setReset(reset: ResetPeriod) {
    // Keep shape valid: unlimited → quantity = null, otherwise ensure a number.
    if (reset === "unlimited") {
      onChange({ reset_period: reset, quantity: null })
    } else {
      onChange({ reset_period: reset, quantity: row.quantity ?? 1 })
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
        {/* Class selector (5 cols) */}
        <div className="md:col-span-5">
          <label className="mb-1 block text-xs font-medium text-gray-600">סוג שיעור</label>
          <select
            value={row.class_id ?? ""}
            onChange={(e) => onChange({ class_id: e.target.value || null })}
            className={inputClass}
          >
            <option value="">כל השיעורים</option>
            {classes
              .filter((c) => c.is_active || c.id === row.class_id)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {!c.is_active ? " (לא פעיל)" : ""}
                </option>
              ))}
          </select>
        </div>

        {/* Quantity (3 cols, hidden when unlimited) */}
        <div className="md:col-span-3">
          <label className="mb-1 block text-xs font-medium text-gray-600">כמות</label>
          {isUnlimited ? (
            <div className="flex h-[38px] items-center rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 text-xs text-gray-400">
              ללא הגבלה
            </div>
          ) : (
            <input
              type="number"
              min={1}
              required
              value={row.quantity ?? ""}
              onChange={(e) =>
                onChange({
                  quantity: e.target.value ? parseInt(e.target.value, 10) : null,
                })
              }
              placeholder="3"
              className={inputClass}
            />
          )}
        </div>

        {/* Reset period (3 cols) */}
        <div className="md:col-span-3">
          <label className="mb-1 block text-xs font-medium text-gray-600">תקופת איפוס</label>
          <select
            value={row.reset_period}
            onChange={(e) => setReset(e.target.value as ResetPeriod)}
            className={inputClass}
          >
            {RESET_PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        {/* Remove button (1 col) */}
        <div className="flex items-end md:col-span-1">
          <button
            type="button"
            onClick={onRemove}
            aria-label="הסר הרשאה"
            className="h-[38px] w-full rounded-lg border border-gray-200 text-gray-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
          >
            ×
          </button>
        </div>
      </div>

      <p className="mt-2 text-xs text-gray-400">
        {RESET_PERIODS.find((p) => p.value === row.reset_period)?.helper}
      </p>
    </div>
  )
}
