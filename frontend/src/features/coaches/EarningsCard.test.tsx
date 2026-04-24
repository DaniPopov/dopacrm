import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { EarningsCard, formatMoney, payModelLabel } from "./EarningsCard"
import type { EarningsBreakdown } from "./types"

const base: EarningsBreakdown = {
  coach_id: "c1",
  from: "2026-05-01",
  to: "2026-05-31",
  effective_from: "2026-05-01",
  effective_to: "2026-05-31",
  currency: "ILS",
  total_cents: 150000,
  by_link: [
    {
      class_id: "b1",
      class_name: "Boxing",
      role: "ראשי",
      pay_model: "per_attendance",
      pay_amount_cents: 5000,
      cents: 100000,
      unit_count: 20,
    },
    {
      class_id: "w1",
      class_name: "Wrestling",
      role: "עוזר",
      pay_model: "fixed",
      pay_amount_cents: 50000,
      cents: 50000,
      unit_count: 31,
    },
  ],
  by_class_cents: { b1: 100000, w1: 50000 },
  by_pay_model_cents: { per_attendance: 100000, fixed: 50000 },
}

describe("EarningsCard", () => {
  it("renders total at the top", () => {
    render(<EarningsCard data={base} />)
    const total = screen.getByText((s) => s.includes("1,500"))
    expect(total).toBeInTheDocument()
  })

  it("renders one row per link", () => {
    render(<EarningsCard data={base} />)
    expect(screen.getByText("Boxing")).toBeInTheDocument()
    expect(screen.getByText("Wrestling")).toBeInTheDocument()
    expect(screen.getByText("20")).toBeInTheDocument() // unit count
    expect(screen.getByText("31")).toBeInTheDocument()
  })

  it("shows empty-state when no links", () => {
    render(
      <EarningsCard
        data={{
          ...base,
          total_cents: 0,
          by_link: [],
          by_class_cents: {},
          by_pay_model_cents: {},
        }}
      />,
    )
    expect(screen.getByText("אין שיעורים מוקצים בטווח זה")).toBeInTheDocument()
  })
})

describe("formatMoney", () => {
  it("renders ILS currency", () => {
    const out = formatMoney(150000, "ILS")
    expect(out).toMatch(/1,500/)
  })

  it("falls back gracefully on unknown currency", () => {
    const out = formatMoney(100, "XYZ")
    expect(out).toContain("1")
  })
})

describe("payModelLabel", () => {
  it("maps each enum to a Hebrew label", () => {
    expect(payModelLabel("fixed")).toBe("משכורת קבועה")
    expect(payModelLabel("per_session")).toBe("לפי שיעור")
    expect(payModelLabel("per_attendance")).toBe("לפי כניסה")
  })

  it("returns the input for unknown models", () => {
    expect(payModelLabel("mystery")).toBe("mystery")
  })
})
