import { describe, it, expect } from "vitest"
import {
  ApiError,
  humanizeLoginError,
  humanizeTenantError,
  humanizeUploadError,
} from "./api-errors"

describe("ApiError", () => {
  it("carries the status code", () => {
    const err = new ApiError("boom", 429)
    expect(err.status).toBe(429)
    expect(err.message).toBe("boom")
    expect(err.name).toBe("ApiError")
    expect(err instanceof Error).toBe(true)
  })
})

describe("humanizeLoginError", () => {
  it("returns wrong-credentials message for 401", () => {
    expect(humanizeLoginError(new ApiError("x", 401))).toBe("שגיאה במייל או סיסמה")
  })

  it("returns suspended-account message for 403", () => {
    expect(humanizeLoginError(new ApiError("x", 403))).toBe("החשבון מושהה, פנו למנהל המערכת")
  })

  it("returns too-many-attempts message for 429", () => {
    expect(humanizeLoginError(new ApiError("x", 429))).toBe("יותר מדי ניסיונות, נסו שוב בעוד דקה")
  })

  it("returns system-error message for 500", () => {
    expect(humanizeLoginError(new ApiError("x", 500))).toBe(
      "שגיאת מערכת, נסו שוב בעוד מספר רגעים",
    )
  })

  it("returns network message for status 0", () => {
    expect(humanizeLoginError(new ApiError("network", 0))).toBe(
      "אין חיבור לשרת, בדקו את החיבור לאינטרנט",
    )
  })

  it("returns generic message for unknown errors", () => {
    expect(humanizeLoginError(new Error("???"))).toBe("שגיאה בהתחברות, נסו שוב")
    expect(humanizeLoginError("not even an error")).toBe("שגיאה בהתחברות, נסו שוב")
  })
})

describe("humanizeTenantError", () => {
  it("returns slug-taken message for 409", () => {
    expect(humanizeTenantError(new ApiError("dup", 409))).toBe(
      "מזהה URL (slug) כבר תפוס, בחרו אחר",
    )
  })

  it("returns validation message for 422", () => {
    expect(humanizeTenantError(new ApiError("x", 422))).toBe(
      "הפרטים שהוזנו אינם תקינים, בדקו את הטופס",
    )
  })

  it("returns system-error message for 500", () => {
    expect(humanizeTenantError(new ApiError("x", 500))).toBe(
      "שגיאת מערכת, נסו שוב בעוד מספר רגעים",
    )
  })

  it("returns generic message for unknown errors", () => {
    expect(humanizeTenantError(undefined)).toBe("אירעה שגיאה בשמירת הנתונים")
  })
})

describe("humanizeUploadError", () => {
  it("returns too-large message for 413", () => {
    expect(humanizeUploadError(new ApiError("x", 413))).toBe("הלוגו גדול מדי (מקסימום 2MB)")
  })

  it("returns unsupported-type message for 415", () => {
    expect(humanizeUploadError(new ApiError("x", 415))).toBe(
      "סוג הקובץ אינו נתמך (PNG, JPG, WebP או SVG)",
    )
  })

  it("returns system-error message for 500", () => {
    expect(humanizeUploadError(new ApiError("x", 500))).toBe(
      "שגיאת מערכת, נסו שוב בעוד מספר רגעים",
    )
  })

  it("returns generic message for unknown errors", () => {
    expect(humanizeUploadError(null)).toBe("אירעה שגיאה בהעלאת הקובץ")
  })
})
