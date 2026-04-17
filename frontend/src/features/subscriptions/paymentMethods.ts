import type { PaymentMethod } from "./types"

/**
 * Canonical Hebrew labels for payment-method keys.
 * Shared by enroll / renew dialogs + the current-sub card + the timeline.
 * Keep in sync with backend ``PaymentMethod`` StrEnum.
 */
export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: "מזומן",
  credit_card: "אשראי",
  standing_order: "הוראת קבע",
  other: "אחר",
}

export const PAYMENT_METHOD_OPTIONS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: PAYMENT_METHOD_LABELS.cash },
  { value: "credit_card", label: PAYMENT_METHOD_LABELS.credit_card },
  { value: "standing_order", label: PAYMENT_METHOD_LABELS.standing_order },
  { value: "other", label: PAYMENT_METHOD_LABELS.other },
]

/**
 * Display string for a sub's current payment info.
 * - `cash` → "מזומן"
 * - `credit_card` + detail → "אשראי — Visa 1234"
 * - `other` + detail → "אחר — bank transfer"
 */
export function formatPaymentMethod(
  method: PaymentMethod,
  detail: string | null | undefined,
): string {
  const label = PAYMENT_METHOD_LABELS[method]
  if (detail && detail.trim().length > 0) {
    return `${label} — ${detail}`
  }
  return label
}
