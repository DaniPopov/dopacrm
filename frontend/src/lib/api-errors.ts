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
