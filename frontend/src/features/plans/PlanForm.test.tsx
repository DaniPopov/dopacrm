import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import PlanForm from "./PlanForm"
import type { MembershipPlan } from "./types"

/**
 * PlanForm — create/edit form + entitlements builder.
 *
 * Covers:
 * - required name field + placeholder
 * - submit normalizes price in שקלים → אגורות (450 → 45000)
 * - type=recurring exposes "תדירות חיוב"; type=one_time exposes duration_days
 * - switching to one_time auto-sets billing_period="one_time"
 * - empty entitlements shows the "ללא הגבלה" hint
 * - "+ הוסף הרשאה" adds a row
 * - picking reset="ללא הגבלה" hides the quantity input
 * - "הסר הרשאה" removes the row
 * - edit mode prefills name, description, price, entitlements
 * - error prop renders
 * - submit button respects `submitting`
 */

vi.mock("@/features/classes/hooks", () => ({
  useClasses: vi.fn(() => ({
    data: [
      { id: "cl1", name: "ספינינג", is_active: true },
      { id: "cl2", name: "יוגה", is_active: true },
    ],
    isLoading: false,
    error: null,
  })),
}))

function renderForm(props: Parameters<typeof PlanForm>[0]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PlanForm {...props} />
    </QueryClientProvider>,
  )
}

const fakePlan: MembershipPlan = {
  id: "p1",
  tenant_id: "t1",
  name: "חודשי",
  description: "מסלול מתחדש",
  type: "recurring",
  price_cents: 45000,
  currency: "ILS",
  billing_period: "monthly",
  duration_days: null,
  is_active: true,
  custom_attrs: {},
  entitlements: [
    {
      id: "e1",
      plan_id: "p1",
      class_id: "cl2",
      quantity: 3,
      reset_period: "weekly",
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

describe("PlanForm — create mode", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders required-field star on name", () => {
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })
    expect(screen.getByText("שם המסלול *")).toBeInTheDocument()
  })

  it("submits with name, price (אגורות), and empty entitlements by default", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderForm({
      submitLabel: "צור מסלול",
      onSubmit,
      onCancel: vi.fn(),
    })

    const nameInput = container.querySelector(
      'input[placeholder*="חודשי"]',
    ) as HTMLInputElement
    const priceInput = container.querySelector(
      'input[type="number"]',
    ) as HTMLInputElement
    await user.type(nameInput, "בסיסי")
    await user.clear(priceInput)
    await user.type(priceInput, "450")

    await user.click(screen.getByRole("button", { name: "צור מסלול" }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const values = onSubmit.mock.calls[0][0]
    expect(values.name).toBe("בסיסי")
    expect(values.price_cents).toBe(45000)
    expect(values.currency).toBe("ILS")
    expect(values.type).toBe("recurring")
    expect(values.billing_period).toBe("monthly")
    expect(values.duration_days).toBeNull()
    expect(values.entitlements).toEqual([])
  })

  it("recurring shows 'תדירות חיוב'; switching to one_time shows duration_days", async () => {
    const user = userEvent.setup()
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })

    expect(screen.getByText("תדירות חיוב *")).toBeInTheDocument()
    expect(screen.queryByText(/תוקף \(בימים\)/)).not.toBeInTheDocument()

    // Flip the "סוג" select to "חד-פעמי"
    const typeSelect = screen.getByDisplayValue("מתחדש")
    await user.selectOptions(typeSelect, "one_time")

    expect(screen.getByText(/תוקף \(בימים\)/)).toBeInTheDocument()
    expect(screen.queryByText("תדירות חיוב *")).not.toBeInTheDocument()
  })

  it("one_time submit includes duration_days + billing_period=one_time", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderForm({
      submitLabel: "צור מסלול",
      onSubmit,
      onCancel: vi.fn(),
    })

    const nameInput = container.querySelector(
      'input[placeholder*="חודשי"]',
    ) as HTMLInputElement
    await user.type(nameInput, "שבועיים")

    const typeSelect = screen.getByDisplayValue("מתחדש")
    await user.selectOptions(typeSelect, "one_time")

    // duration_days defaults to 30; override just to be explicit
    const durationInput = screen.getByPlaceholderText("30") as HTMLInputElement
    await user.clear(durationInput)
    await user.type(durationInput, "14")

    // Need to fill price
    const priceInputs = container.querySelectorAll('input[type="number"]')
    // Two number inputs visible: price + duration. Use the first one for price.
    const priceInput = priceInputs[0] as HTMLInputElement
    await user.clear(priceInput)
    await user.type(priceInput, "200")

    await user.click(screen.getByRole("button", { name: "צור מסלול" }))
    const values = onSubmit.mock.calls[0][0]
    expect(values.type).toBe("one_time")
    expect(values.billing_period).toBe("one_time")
    expect(values.duration_days).toBe(14)
    expect(values.price_cents).toBe(20000)
  })

  it("empty entitlements shows the unlimited hint", () => {
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })
    expect(
      screen.getByText(/המנויים יכולים להיכנס לכל שיעור ללא מכסה/),
    ).toBeInTheDocument()
  })

  it("'+ הוסף הרשאה' adds a row with class selector + quantity + reset", async () => {
    const user = userEvent.setup()
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })

    await user.click(screen.getByRole("button", { name: /הוסף הרשאה/ }))

    expect(screen.getByText("סוג שיעור")).toBeInTheDocument()
    expect(screen.getByText("כמות")).toBeInTheDocument()
    expect(screen.getByText("תקופת איפוס")).toBeInTheDocument()
  })

  it("picking reset='ללא הגבלה' hides the quantity input + sets quantity=null on submit", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderForm({
      submitLabel: "צור מסלול",
      onSubmit,
      onCancel: vi.fn(),
    })

    const nameInput = container.querySelector(
      'input[placeholder*="חודשי"]',
    ) as HTMLInputElement
    await user.type(nameInput, "Free-for-all")

    // Fill price
    const priceInput = container.querySelector(
      'input[type="number"]',
    ) as HTMLInputElement
    await user.clear(priceInput)
    await user.type(priceInput, "100")

    await user.click(screen.getByRole("button", { name: /הוסף הרשאה/ }))
    // The reset-period select is the second <select> after class select; use display value.
    const resetSelect = screen.getByDisplayValue("שבועי") as HTMLSelectElement
    await user.selectOptions(resetSelect, "unlimited")

    expect(screen.getByText("ללא הגבלה", { selector: "div" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "צור מסלול" }))
    const values = onSubmit.mock.calls[0][0]
    expect(values.entitlements).toHaveLength(1)
    expect(values.entitlements[0].quantity).toBeNull()
    expect(values.entitlements[0].reset_period).toBe("unlimited")
  })

  it("'הסר הרשאה' removes the row", async () => {
    const user = userEvent.setup()
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })

    await user.click(screen.getByRole("button", { name: /הוסף הרשאה/ }))
    expect(screen.getByText("סוג שיעור")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "הסר הרשאה" }))
    expect(screen.queryByText("סוג שיעור")).not.toBeInTheDocument()
  })

  it("cancel fires onCancel without submitting", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    renderForm({
      submitLabel: "צור מסלול",
      onSubmit,
      onCancel,
    })
    await user.click(screen.getByRole("button", { name: "ביטול" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("disables submit while submitting=true", () => {
    renderForm({
      submitting: true,
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })
    expect(screen.getByRole("button", { name: "שומר..." })).toBeDisabled()
  })
})

describe("PlanForm — edit mode", () => {
  it("prefills name, description, and the existing entitlement row", () => {
    const { container } = renderForm({
      initial: fakePlan,
      submitLabel: "שמור שינויים",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })
    const nameInput = container.querySelector(
      'input[placeholder*="חודשי"]',
    ) as HTMLInputElement
    expect(nameInput.value).toBe("חודשי")
    expect((container.querySelector("textarea") as HTMLTextAreaElement).value).toBe(
      "מסלול מתחדש",
    )
    // Price displayed as 450 (שקלים)
    const priceInput = container.querySelector(
      'input[type="number"]',
    ) as HTMLInputElement
    expect(priceInput.value).toBe("450")
    // Entitlement row is visible
    expect(screen.getByText("סוג שיעור")).toBeInTheDocument()
  })
})

describe("PlanForm — error display", () => {
  it("renders the Hebrew error when `error` prop is set", () => {
    renderForm({
      error: "מסלול בשם זה כבר קיים בחדר הכושר",
      submitLabel: "צור מסלול",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    })
    expect(
      screen.getByText("מסלול בשם זה כבר קיים בחדר הכושר"),
    ).toBeInTheDocument()
  })
})
