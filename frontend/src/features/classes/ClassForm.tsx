import { useState, type FormEvent } from "react"
import type { CreateGymClassRequest, GymClass } from "./types"

export interface ClassFormValues extends CreateGymClassRequest {}

/**
 * Shared create/edit form for a gym class type.
 *
 * Fields:
 * - name (required, unique within tenant)
 * - description (optional textarea)
 * - color (optional hex, free text — no validation)
 *
 * Used by both the inline create card on the list page and the
 * standalone edit page.
 */
export default function ClassForm({
  initial,
  submitting,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  /** Values to prefill in edit mode; omit for create. */
  initial?: Partial<GymClass>
  /** True while the mutation is in flight. */
  submitting?: boolean
  /** Hebrew user-facing error to show above the buttons. */
  error?: string | null
  /** Primary action button text (e.g. "צור שיעור" / "שמור שינויים"). */
  submitLabel: string
  /** Called with the form values on submit. */
  onSubmit: (values: ClassFormValues) => void
  /** Called when the user clicks the cancel button. */
  onCancel: () => void
}) {
  const [form, setForm] = useState<ClassFormValues>({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    color: initial?.color ?? "",
  })

  function set<K extends keyof ClassFormValues>(
    key: K,
    value: ClassFormValues[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit({
      name: form.name,
      description: form.description || null,
      color: form.color || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Field label="שם השיעור *">
        <input
          type="text"
          required
          maxLength={100}
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="ספינינג"
          className={inputClass}
        />
      </Field>

      <Field label="תיאור">
        <textarea
          rows={3}
          value={form.description ?? ""}
          onChange={(e) => set("description", e.target.value)}
          placeholder="שיעור רכיבה עצים בפנים"
          className={`${inputClass} resize-y`}
        />
      </Field>

      <Field label="צבע" helper="בחרו מהפלטה או לחצו על הריבוע האחרון לבחירה חופשית">
        <ColorPicker
          value={form.color ?? ""}
          onChange={(value) => set("color", value)}
        />
      </Field>

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

/** Label + optional helper + input wrapper. */
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

/* ── Color picker ─────────────────────────────────────────────

   Preset palette + free-picker fallback. Owners don't have to know
   what a hex code is — they click a colored swatch. The last swatch
   is a multi-color gradient that opens the browser's native color
   picker (<input type="color">) for anyone who wants something
   specific. The picker's value is mirrored back to state as "#rrggbb".

   Palette chosen for gym-class-type typical use:
   - calm tones (yoga, pilates): emerald, cyan, indigo
   - energetic (spinning, HIIT): blue, red, orange, amber
   - versatile: purple, pink, gray

   If adding/removing colors, keep the count divisible by the grid
   column count (currently 6) so the layout stays tidy.
───────────────────────────────────────────────────────────────── */

const PRESET_COLORS: { hex: string; label: string }[] = [
  { hex: "#3B82F6", label: "כחול" },
  { hex: "#10B981", label: "ירוק" },
  { hex: "#EF4444", label: "אדום" },
  { hex: "#F97316", label: "כתום" },
  { hex: "#F59E0B", label: "צהוב" },
  { hex: "#8B5CF6", label: "סגול" },
  { hex: "#EC4899", label: "ורוד" },
  { hex: "#06B6D4", label: "טורקיז" },
  { hex: "#6366F1", label: "אינדיגו" },
  { hex: "#84CC16", label: "ליים" },
  { hex: "#6B7280", label: "אפור" },
]

/**
 * Color picker with a preset palette + "custom" fallback.
 *
 * - Click a preset → sets color to that hex.
 * - Click the "custom" tile (rainbow gradient + pipette icon) → opens
 *   the native `<input type="color">` picker for arbitrary hex values.
 * - A "clear" chip at the end resets color to empty.
 *
 * Fully keyboard navigable: each preset is a real `<button>`, the
 * custom picker is a hidden `<input>` triggered via its label, and
 * the selected state shows a ring around the chosen swatch.
 */
function ColorPicker({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const isCustomColor = value !== "" && !PRESET_COLORS.some((p) => p.hex === value)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-6 gap-2 sm:grid-cols-6 md:grid-cols-12">
        {PRESET_COLORS.map((preset) => {
          const selected = value === preset.hex
          return (
            <button
              key={preset.hex}
              type="button"
              onClick={() => onChange(preset.hex)}
              title={preset.label}
              aria-label={preset.label}
              aria-pressed={selected}
              className={`relative h-9 w-9 rounded-lg border transition-all ${
                selected
                  ? "border-gray-900 ring-2 ring-gray-900 ring-offset-2"
                  : "border-gray-200 hover:scale-110"
              }`}
              style={{ backgroundColor: preset.hex }}
            >
              {selected && (
                <span className="absolute inset-0 flex items-center justify-center text-white drop-shadow">
                  ✓
                </span>
              )}
            </button>
          )
        })}

        {/* Custom picker — hidden input, rainbow swatch as visible trigger */}
        <label
          title="בחירה חופשית"
          aria-label="בחירה חופשית"
          className={`relative flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border transition-all ${
            isCustomColor
              ? "border-gray-900 ring-2 ring-gray-900 ring-offset-2"
              : "border-gray-200 hover:scale-110"
          }`}
          style={{
            background: isCustomColor
              ? value
              : "conic-gradient(from 0deg, #EF4444, #F59E0B, #10B981, #06B6D4, #3B82F6, #8B5CF6, #EC4899, #EF4444)",
          }}
        >
          <input
            type="color"
            value={/^#[0-9A-Fa-f]{6}$/.test(value) ? value : "#3B82F6"}
            onChange={(e) => onChange(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
            aria-label="בחירת צבע חופשית"
          />
          {isCustomColor && (
            <span className="text-white drop-shadow">✓</span>
          )}
        </label>
      </div>

      {/* Selected value display + clear */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        {value ? (
          <>
            <span>נבחר:</span>
            <span className="font-mono" dir="ltr">
              {value}
            </span>
            <button
              type="button"
              onClick={() => onChange("")}
              className="mr-1 text-gray-400 hover:text-red-600"
              aria-label="נקה צבע"
            >
              × ניקוי
            </button>
          </>
        ) : (
          <span>לא נבחר צבע</span>
        )}
      </div>
    </div>
  )
}
