import { describe, it, expect } from "vitest"
import {
  ApiError,
  humanizeClassError,
  humanizeLeadError,
  humanizeLoginError,
  humanizeMemberError,
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

  it("returns slug-format message when backend reports slug_invalid_format", () => {
    expect(
      humanizeTenantError(new ApiError("Value error, slug_invalid_format", 422)),
    ).toBe("מזהה URL (slug) חייב להיות באנגלית קטנה, ספרות ומקפים בלבד")
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

describe("humanizeMemberError", () => {
  it("returns not-found message for 404", () => {
    expect(humanizeMemberError(new ApiError("x", 404))).toBe("המנוי לא נמצא")
  })

  it("returns phone-collision message when 409 mentions 'already exists'", () => {
    expect(
      humanizeMemberError(
        new ApiError("Member with phone already exists in this tenant: +972-50-1", 409),
      ),
    ).toBe("מנוי עם מספר טלפון זה כבר קיים")
  })

  it("returns transition message when 409 mentions 'Cannot'", () => {
    expect(
      humanizeMemberError(new ApiError("Cannot freeze member in status 'frozen'", 409)),
    ).toBe("לא ניתן לבצע פעולה זו בסטטוס הנוכחי")
  })

  it("returns generic conflict for other 409s", () => {
    expect(humanizeMemberError(new ApiError("something else", 409))).toBe(
      "התנגשות — בדקו שהפרטים אינם חוזרים",
    )
  })

  it("returns validation message for 422", () => {
    expect(humanizeMemberError(new ApiError("x", 422))).toBe(
      "הפרטים שהוזנו אינם תקינים, בדקו את הטופס",
    )
  })

  it("returns generic message for non-ApiError", () => {
    expect(humanizeMemberError(null)).toBe("אירעה שגיאה בשמירת המנוי")
  })
})

describe("humanizeClassError", () => {
  it("returns owner-only message for 403", () => {
    expect(humanizeClassError(new ApiError("x", 403))).toBe(
      "רק בעלים יכולים לערוך שיעורים",
    )
  })

  it("returns not-found message for 404", () => {
    expect(humanizeClassError(new ApiError("x", 404))).toBe("השיעור לא נמצא")
  })

  it("returns duplicate-name message for 409", () => {
    expect(humanizeClassError(new ApiError("dup", 409))).toBe(
      "שיעור בשם זה כבר קיים בחדר הכושר",
    )
  })

  it("returns validation message for 422", () => {
    expect(humanizeClassError(new ApiError("x", 422))).toBe(
      "הפרטים שהוזנו אינם תקינים, בדקו את הטופס",
    )
  })

  it("returns generic message for non-ApiError", () => {
    expect(humanizeClassError(null)).toBe("אירעה שגיאה בשמירת השיעור")
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

describe("humanizeLeadError", () => {
  it("returns FEATURE_DISABLED message for 403 with that code", () => {
    expect(humanizeLeadError(new ApiError("FEATURE_DISABLED", 403))).toBe(
      "תכונת לידים אינה זמינה לחדר כושר זה. פנו למנהל המערכת",
    )
  })

  it("returns 'lead not found' for 404", () => {
    expect(humanizeLeadError(new ApiError("LEAD_NOT_FOUND", 404))).toBe(
      "הליד לא נמצא",
    )
  })

  it("returns 'already converted' for 409 LEAD_ALREADY_CONVERTED", () => {
    expect(humanizeLeadError(new ApiError("LEAD_ALREADY_CONVERTED", 409))).toBe(
      "הליד כבר הומר למנוי",
    )
  })

  it("returns transition message for 409 INVALID_LEAD_STATUS_TRANSITION", () => {
    expect(
      humanizeLeadError(new ApiError("INVALID_LEAD_STATUS_TRANSITION", 409)),
    ).toBe("לא ניתן לבצע מעבר זה במצב הנוכחי של הליד")
  })

  it("returns phone collision message for 409 MEMBER_ALREADY_EXISTS (convert)", () => {
    expect(humanizeLeadError(new ApiError("MEMBER_ALREADY_EXISTS", 409))).toBe(
      "מנוי עם מספר טלפון זה כבר קיים. בדקו אם זה אותו אדם.",
    )
  })

  it("returns plan-tenant-mismatch message for 422 SUBSCRIPTION_PLAN_TENANT_MISMATCH", () => {
    expect(
      humanizeLeadError(new ApiError("SUBSCRIPTION_PLAN_TENANT_MISMATCH", 422)),
    ).toBe("המסלול שנבחר אינו שייך לחדר כושר זה")
  })

  it("returns plan-not-found message for 404 PLAN_NOT_FOUND", () => {
    expect(humanizeLeadError(new ApiError("PLAN_NOT_FOUND", 404))).toBe(
      "המסלול לא נמצא",
    )
  })

  it("returns generic 422 message for unhandled validation errors", () => {
    expect(humanizeLeadError(new ApiError("x", 422))).toBe(
      "הפרטים שהוזנו אינם תקינים, בדקו את הטופס",
    )
  })

  it("returns generic message for non-ApiError", () => {
    expect(humanizeLeadError(null)).toBe("אירעה שגיאה בליד")
  })
})
