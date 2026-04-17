import { describe, it, expect } from "vitest"
import {
  PAYMENT_METHOD_LABELS,
  PAYMENT_METHOD_OPTIONS,
  formatPaymentMethod,
} from "./paymentMethods"

describe("paymentMethods", () => {
  it("maps every enum key to a Hebrew label", () => {
    expect(PAYMENT_METHOD_LABELS.cash).toBe("מזומן")
    expect(PAYMENT_METHOD_LABELS.credit_card).toBe("אשראי")
    expect(PAYMENT_METHOD_LABELS.standing_order).toBe("הוראת קבע")
    expect(PAYMENT_METHOD_LABELS.other).toBe("אחר")
  })

  it("PAYMENT_METHOD_OPTIONS lists all 4 methods in a canonical order", () => {
    expect(PAYMENT_METHOD_OPTIONS.map((o) => o.value)).toEqual([
      "cash",
      "credit_card",
      "standing_order",
      "other",
    ])
  })

  describe("formatPaymentMethod", () => {
    it("shows label only when detail is null", () => {
      expect(formatPaymentMethod("cash", null)).toBe("מזומן")
    })
    it("shows label only when detail is empty whitespace", () => {
      expect(formatPaymentMethod("cash", "   ")).toBe("מזומן")
    })
    it("appends detail after an em dash", () => {
      expect(formatPaymentMethod("credit_card", "Visa 1234")).toBe("אשראי — Visa 1234")
    })
    it("works for 'other' with free text", () => {
      expect(formatPaymentMethod("other", "bank transfer")).toBe("אחר — bank transfer")
    })
  })
})
