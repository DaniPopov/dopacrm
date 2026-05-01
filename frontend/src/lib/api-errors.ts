/**
 * Shared helpers for converting API errors into Hebrew user-facing messages.
 *
 * Every feature's error handling should go through here so we have one place
 * to update wording / add new status codes.
 *
 * The ApiError class carries the HTTP status (0 = network failure), letting
 * the UI show specific messages per category instead of raw backend details.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

/** Generic error → Hebrew message fallback table. */
function genericMessage(status: number): string {
  if (status === 0) return "אין חיבור לשרת, בדקו את החיבור לאינטרנט"
  if (status === 401) return "נדרשת התחברות מחדש"
  if (status === 403) return "אין לכם הרשאה לפעולה זו"
  if (status === 404) return "הפריט לא נמצא"
  if (status === 409) return "הפריט כבר קיים"
  if (status === 413) return "הקובץ גדול מדי"
  if (status === 415) return "סוג הקובץ אינו נתמך"
  if (status === 422) return "הפרטים שהוזנו אינם תקינים"
  if (status === 429) return "יותר מדי בקשות, נסו שוב בעוד מספר שניות"
  if (status >= 500) return "שגיאת מערכת, נסו שוב בעוד מספר רגעים"
  return "אירעה שגיאה, נסו שוב"
}

/**
 * Domain-specific overrides for login errors.
 * Call this from the LoginPage catch block.
 */
export function humanizeLoginError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 401) return "שגיאה במייל או סיסמה"
    if (status === 403) return "החשבון מושהה, פנו למנהל המערכת"
    if (status === 429) return "יותר מדי ניסיונות, נסו שוב בעוד דקה"
    return genericMessage(status)
  }
  return "שגיאה בהתחברות, נסו שוב"
}

/**
 * Overrides for tenant create/update errors.
 * Call this from the tenant form catch block.
 *
 * 422 validation errors are inspected for known machine-readable codes
 * in the backend's error detail so we can show a targeted Hebrew message
 * (e.g. `slug_invalid_format` becomes a rule-of-thumb for the slug field).
 */
export function humanizeTenantError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    const message = (err as ApiError).message
    if (status === 409) return "מזהה URL (slug) כבר תפוס, בחרו אחר"
    if (status === 422) {
      // Backend embeds machine-readable codes in the detail — match them here.
      if (message.includes("slug_invalid_format")) {
        return "מזהה URL (slug) חייב להיות באנגלית קטנה, ספרות ומקפים בלבד"
      }
      return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    }
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת הנתונים"
}

/**
 * Overrides for member CRUD errors (create / update / freeze / cancel).
 *
 * The backend differentiates phone collision (MEMBER_ALREADY_EXISTS) from
 * invalid state transitions (MEMBER_INVALID_TRANSITION) via the detail
 * message — we sniff both keywords rather than making the error shape
 * richer.
 */
export function humanizeMemberError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    const message = (err as ApiError).message
    if (status === 404) return "המנוי לא נמצא"
    if (status === 409) {
      if (message.toLowerCase().includes("already exists")) {
        return "מנוי עם מספר טלפון זה כבר קיים"
      }
      if (message.toLowerCase().includes("cannot ")) {
        return "לא ניתן לבצע פעולה זו בסטטוס הנוכחי"
      }
      return "התנגשות — בדקו שהפרטים אינם חוזרים"
    }
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת המנוי"
}

/**
 * Overrides for class-catalog errors (create / update / deactivate).
 *
 * Owner is the only role allowed to mutate — staff seeing 403 means
 * the UI rendered them an edit button it shouldn't have.
 */
export function humanizeClassError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 403) return "רק בעלים יכולים לערוך שיעורים"
    if (status === 404) return "השיעור לא נמצא"
    if (status === 409) return "שיעור בשם זה כבר קיים בחדר הכושר"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת השיעור"
}

/**
 * Overrides for attendance errors (record / undo / quota-check).
 *
 * Two 409 cases are "business" responses that the UI handles inline
 * (override modal) rather than toasts:
 *   - ATTENDANCE_QUOTA_EXCEEDED
 *   - ATTENDANCE_CLASS_NOT_COVERED
 * For those, the UI should show the override dialog, not this string.
 * Other 409s (MEMBER_NO_ACTIVE_SUBSCRIPTION, UNDO_WINDOW_EXPIRED,
 * ALREADY_UNDONE) are genuine errors → fall through to a toast-friendly
 * Hebrew message.
 */
export function humanizeAttendanceError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    const message = (err as ApiError).message.toLowerCase()
    if (status === 403) return "אין לכם הרשאה לפעולה זו"
    if (status === 404) return "הפריט לא נמצא"
    if (status === 409) {
      if (message.includes("no active subscription"))
        return "למנוי זה אין מנוי פעיל. יש להרשום תחילה"
      if (message.includes("undo window"))
        return "חלון הביטול (24 שעות) פג"
      if (message.includes("already undone"))
        return "הכניסה כבר בוטלה"
      if (message.includes("quota exceeded"))
        return "המנוי מיצה את המכסה לתקופה"
      if (message.includes("not covered"))
        return "השיעור לא כלול במסלול"
      return "לא ניתן לבצע פעולה זו"
    }
    if (status === 422) return "הפרטים שהוזנו אינם תקינים"
    return genericMessage(status)
  }
  return "אירעה שגיאה ברישום הכניסה"
}

/**
 * Overrides for subscription CRUD errors (enroll / freeze / renew / change-plan / cancel).
 *
 * Status-code semantics:
 * - 403: staff-gated op performed by sales or super_admin
 * - 404: sub not found OR in another tenant (server returns 404 either way)
 * - 409: either a state-machine violation OR "member already has active sub"
 *        OR "change-plan with same plan". Backend detail differentiates.
 * - 422: invalid input shape
 */
export function humanizeSubscriptionError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    const message = (err as ApiError).message.toLowerCase()
    if (status === 403) return "אין לכם הרשאה לפעולה זו"
    if (status === 404) return "המנוי לא נמצא"
    if (status === 409) {
      if (message.includes("already")) return "למנוי זה כבר יש מנוי פעיל"
      if (message.includes("same plan")) return "יש לבחור מסלול שונה מהנוכחי"
      return "לא ניתן לבצע פעולה זו בסטטוס הנוכחי"
    }
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בעדכון המנוי"
}

/**
 * Overrides for membership-plan CRUD errors (create / update / deactivate).
 *
 * The backend returns PLAN_INVALID_SHAPE (422) for bad combos like
 * one_time + no duration_days, or unlimited + quantity. We collapse all
 * 422s into one generic message — the form itself guides the owner to
 * valid combinations, so a detailed field-level error isn't useful.
 */
export function humanizePlanError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 403) return "רק בעלים יכולים לערוך מסלולים"
    if (status === 404) return "המסלול לא נמצא"
    if (status === 409) return "מסלול בשם זה כבר קיים בחדר הכושר"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת המסלול"
}

/**
 * Overrides for user CRUD errors (create/update/delete).
 * Call this from the user form catch block.
 */
export function humanizeUserError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 409) return "משתמש עם מייל זה כבר קיים"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת המשתמש"
}

/**
 * Overrides for upload errors.
 * Call this from any upload flow.
 */
export function humanizeUploadError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 413) return "הלוגו גדול מדי (מקסימום 2MB)"
    if (status === 415) return "סוג הקובץ אינו נתמך (PNG, JPG, WebP או SVG)"
    return genericMessage(status)
  }
  return "אירעה שגיאה בהעלאת הקובץ"
}

/**
 * Overrides for Schedule API errors.
 */
export function humanizeScheduleError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const apiErr = err as ApiError
    const status = apiErr.status
    const msg = apiErr.message
    if (status === 403 && msg.includes("FEATURE_DISABLED"))
      return "תכונת לוח השיעורים אינה זמינה לחדר כושר זה. פנו למנהל המערכת"
    if (status === 404) return "השיעור / התבנית לא נמצאו"
    if (status === 409 && msg.includes("SESSION_TRANSITION"))
      return "לא ניתן לבצע פעולה זו בסטטוס הנוכחי של השיעור"
    if (status === 409) return "לא ניתן לבצע פעולה זו"
    if (status === 422 && msg.includes("INVALID_BULK_RANGE"))
      return "טווח התאריכים לא תקין"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים"
    return genericMessage(status)
  }
  return "אירעה שגיאה בלוח השיעורים"
}

/**
 * Overrides for Leads API errors (CRUD + status + assign + convert + activities).
 *
 * Convert produces the most interesting error space — it can fail with
 * MEMBER_ALREADY_EXISTS (phone collision), an invalid plan
 * (PLAN_NOT_FOUND, SUBSCRIPTION_PLAN_TENANT_MISMATCH), or simply because
 * the lead was already converted (LEAD_ALREADY_CONVERTED). Each gets
 * its own Hebrew copy.
 */
export function humanizeLeadError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const apiErr = err as ApiError
    const status = apiErr.status
    const msg = apiErr.message
    if (status === 403 && msg.includes("FEATURE_DISABLED"))
      return "תכונת לידים אינה זמינה לחדר כושר זה. פנו למנהל המערכת"
    // PLAN_NOT_FOUND surfaces from convert when the picked plan id is
    // gone; check it BEFORE the generic 404 fall-through so the operator
    // sees "plan not found" instead of "lead not found."
    if (status === 404 && msg.includes("PLAN_NOT_FOUND"))
      return "המסלול לא נמצא"
    if (status === 404) return "הליד לא נמצא"
    if (status === 409 && msg.includes("LEAD_ALREADY_CONVERTED"))
      return "הליד כבר הומר למנוי"
    if (status === 409 && msg.includes("INVALID_LEAD_STATUS_TRANSITION"))
      return "לא ניתן לבצע מעבר זה במצב הנוכחי של הליד"
    // Convert-specific errors that bubble up from MemberService / SubscriptionService.
    if (status === 409 && msg.includes("MEMBER_ALREADY_EXISTS"))
      return "מנוי עם מספר טלפון זה כבר קיים. בדקו אם זה אותו אדם."
    if (status === 422 && msg.includes("SUBSCRIPTION_PLAN_TENANT_MISMATCH"))
      return "המסלול שנבחר אינו שייך לחדר כושר זה"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בליד"
}

/**
 * Overrides for Payments API errors (record / refund / list / dashboard).
 *
 * Refund is the most error-rich path:
 *   - 409 PAYMENT_REFUND_EXCEEDS_ORIGINAL → user typed too much; show how
 *     much is actually refundable
 *   - 409 PAYMENT_ALREADY_FULLY_REFUNDED → nothing left to refund;
 *     UI should hide the button rather than show this
 *   - 422 PAYMENT_AMOUNT_INVALID → covers zero / negative / future
 *     paid_at / backdate-without-flag / refund-of-refund
 */
export function humanizePaymentError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const apiErr = err as ApiError
    const status = apiErr.status
    const msg = apiErr.message
    if (status === 403) return "אין לכם הרשאה לפעולה זו"
    if (status === 404) return "התשלום לא נמצא"
    if (status === 409 && msg.includes("PAYMENT_REFUND_EXCEEDS_ORIGINAL"))
      return "סכום ההחזר גדול מהיתרה הניתנת להחזר"
    if (status === 409 && msg.includes("PAYMENT_ALREADY_FULLY_REFUNDED"))
      return "התשלום כבר הוחזר במלואו"
    if (status === 422 && msg.includes("PAYMENT_AMOUNT_INVALID"))
      return "סכום או תאריך התשלום אינם תקינים"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    return genericMessage(status)
  }
  return "אירעה שגיאה בתשלום"
}

/**
 * Overrides for Coaches API errors (CRUD + links + earnings).
 */
export function humanizeCoachError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const apiErr = err as ApiError
    const status = apiErr.status
    const msg = apiErr.message
    if (status === 404) return "המאמן או השיעור לא נמצאו"
    if (status === 409 && msg.includes("COACH_ALREADY_LINKED"))
      return "למאמן זה כבר יש משתמש מחובר"
    if (status === 409 && msg.includes("CLASS_COACH_CONFLICT"))
      return "יש כבר מאמן בתפקיד זה בשיעור זה"
    if (status === 409) return "לא ניתן לבצע פעולה זו בסטטוס הנוכחי"
    if (status === 422 && msg.includes("EARNINGS_RANGE"))
      return "טווח התאריכים לא תקין"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת המאמן"
}
