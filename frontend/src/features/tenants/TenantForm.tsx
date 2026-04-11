import { useState, type FormEvent } from "react"
import { humanizeUploadError } from "@/lib/api-errors"
import { useUploadLogo } from "./hooks"
import type { CreateTenantRequest, Tenant } from "./types"

export interface TenantFormValues extends CreateTenantRequest {
  logo_presigned_url?: string | null
}

interface TenantFormProps {
  initial?: Partial<Tenant>
  submitting?: boolean
  error?: string | null
  submitLabel: string
  onSubmit: (values: TenantFormValues) => void
  onCancel: () => void
}

/**
 * Shared create/edit form for a tenant. Used by both the create card
 * and the edit dialog.
 *
 * Values are managed with plain useState — react-hook-form would be
 * nicer for a bigger form, but for ~15 fields this is simpler and
 * has zero dependencies.
 */
export default function TenantForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: TenantFormProps) {
  const uploadLogo = useUploadLogo()

  const [form, setForm] = useState<TenantFormValues>({
    slug: initial?.slug ?? "",
    name: initial?.name ?? "",
    logo_url: initial?.logo_url ?? null,
    logo_presigned_url: initial?.logo_presigned_url ?? null,
    phone: initial?.phone ?? "",
    email: initial?.email ?? "",
    website: initial?.website ?? "",
    address_street: initial?.address_street ?? "",
    address_city: initial?.address_city ?? "",
    address_country: initial?.address_country ?? "IL",
    address_postal_code: initial?.address_postal_code ?? "",
    legal_name: initial?.legal_name ?? "",
    tax_id: initial?.tax_id ?? "",
    timezone: initial?.timezone ?? "Asia/Jerusalem",
    currency: initial?.currency ?? "ILS",
    locale: initial?.locale ?? "he-IL",
  })

  function setField<K extends keyof TenantFormValues>(key: K, value: TenantFormValues[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  // Auto-generate slug from name when creating (not editing)
  function handleNameChange(v: string) {
    setField("name", v)
    if (!initial?.id) {
      const auto = v
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, "")
        .trim()
        .replace(/\s+/g, "-")
      setField("slug", auto)
    }
  }

  async function handleLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await uploadLogo.mutateAsync(file)
      setField("logo_url", result.key)
      setField("logo_presigned_url", result.presigned_url)
    } catch (err) {
      // upload error is shown via the mutation state below
      console.error("Logo upload failed:", err)
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // Send only fields the backend expects — strip logo_presigned_url
    const { logo_presigned_url: _, ...payload } = form
    onSubmit(payload)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ── Section: identity + branding ───────────────────────── */}
      <Section title="פרטי חדר כושר">
        <Field label="שם *">
          <input
            type="text"
            required
            value={form.name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="IronFit Tel Aviv"
            className={inputClass}
          />
        </Field>
        <Field label="מזהה URL (Slug) *" helper="אותיות לועזיות, מספרים ומקפים">
          <input
            type="text"
            required
            value={form.slug}
            onChange={(e) => setField("slug", e.target.value)}
            placeholder="ironfit-tlv"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="לוגו" className="sm:col-span-2">
          <div className="flex items-center gap-4">
            {form.logo_presigned_url ? (
              <img
                src={form.logo_presigned_url}
                alt="logo preview"
                className="h-16 w-16 rounded-lg border border-gray-200 object-cover"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed border-gray-300 text-xs text-gray-400">
                ללא
              </div>
            )}
            <label className="cursor-pointer">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                onChange={handleLogoChange}
                className="hidden"
              />
              <span className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50">
                {uploadLogo.isPending ? "מעלה..." : "בחרו קובץ"}
              </span>
            </label>
            {uploadLogo.error && (
              <span className="text-xs text-red-600">
                {humanizeUploadError(uploadLogo.error)}
              </span>
            )}
          </div>
        </Field>
      </Section>

      {/* ── Section: contact ───────────────────────────────────── */}
      <Section title="פרטי קשר">
        <Field label="טלפון">
          <input
            type="tel"
            value={form.phone ?? ""}
            onChange={(e) => setField("phone", e.target.value)}
            placeholder="+972-3-555-1234"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="אימייל">
          <input
            type="email"
            value={form.email ?? ""}
            onChange={(e) => setField("email", e.target.value)}
            placeholder="info@ironfit.co.il"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="אתר אינטרנט" className="sm:col-span-2">
          <input
            type="url"
            value={form.website ?? ""}
            onChange={(e) => setField("website", e.target.value)}
            placeholder="https://ironfit.co.il"
            dir="ltr"
            className={inputClass}
          />
        </Field>
      </Section>

      {/* ── Section: address ───────────────────────────────────── */}
      <Section title="כתובת">
        <Field label="רחוב ומספר" className="sm:col-span-2">
          <input
            type="text"
            value={form.address_street ?? ""}
            onChange={(e) => setField("address_street", e.target.value)}
            placeholder="רוטשילד 1"
            className={inputClass}
          />
        </Field>
        <Field label="עיר">
          <input
            type="text"
            value={form.address_city ?? ""}
            onChange={(e) => setField("address_city", e.target.value)}
            placeholder="תל אביב"
            className={inputClass}
          />
        </Field>
        <Field label="מיקוד">
          <input
            type="text"
            value={form.address_postal_code ?? ""}
            onChange={(e) => setField("address_postal_code", e.target.value)}
            placeholder="6578901"
            dir="ltr"
            className={inputClass}
          />
        </Field>
        <Field label="מדינה">
          <select
            value={form.address_country ?? "IL"}
            onChange={(e) => setField("address_country", e.target.value)}
            className={inputClass}
          >
            <option value="IL">ישראל (IL)</option>
            <option value="US">United States (US)</option>
            <option value="GB">United Kingdom (GB)</option>
          </select>
        </Field>
      </Section>

      {/* ── Section: legal ─────────────────────────────────────── */}
      <Section title="פרטים משפטיים">
        <Field label="שם העסק (חוקי)">
          <input
            type="text"
            value={form.legal_name ?? ""}
            onChange={(e) => setField("legal_name", e.target.value)}
            placeholder="IronFit בע״מ"
            className={inputClass}
          />
        </Field>
        <Field label="ח.פ / ע.מ">
          <input
            type="text"
            value={form.tax_id ?? ""}
            onChange={(e) => setField("tax_id", e.target.value)}
            placeholder="123456789"
            dir="ltr"
            className={inputClass}
          />
        </Field>
      </Section>

      {/* ── Section: regional ──────────────────────────────────── */}
      <Section title="הגדרות אזוריות">
        <Field label="אזור זמן">
          <select
            value={form.timezone}
            onChange={(e) => setField("timezone", e.target.value)}
            className={inputClass}
          >
            <option value="Asia/Jerusalem">Asia/Jerusalem</option>
            <option value="America/New_York">America/New_York</option>
            <option value="Europe/London">Europe/London</option>
          </select>
        </Field>
        <Field label="מטבע">
          <select
            value={form.currency}
            onChange={(e) => setField("currency", e.target.value)}
            className={inputClass}
          >
            <option value="ILS">ILS — שקל</option>
            <option value="USD">USD — דולר</option>
            <option value="EUR">EUR — יורו</option>
          </select>
        </Field>
      </Section>

      {/* ── Error + actions ────────────────────────────────────── */}
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
          disabled={submitting || uploadLogo.isPending}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "שומר..." : submitLabel}
        </button>
      </div>
    </form>
  )
}

/* ── Layout helpers ────────────────────────────────────────── */

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-3 text-sm font-semibold text-gray-700">{title}</h4>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </div>
  )
}

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
