import { describe, it, expect } from "vitest"
import {
  canAccess,
  accessibleFeatures,
  GRANTABLE_FEATURES,
  type TenantOverrides,
} from "./permissions"
import type { User, Role } from "./types"

function makeUser(role: Role): User {
  return {
    id: "u1",
    email: `${role}@example.com`,
    role,
    tenant_id: role === "super_admin" ? null : "t1",
    is_active: true,
    oauth_provider: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }
}

describe("canAccess — baseline", () => {
  it("super_admin sees platform features and never gym features", () => {
    const u = makeUser("super_admin")
    expect(canAccess(u, "tenants")).toBe(true)
    expect(canAccess(u, "dashboard")).toBe(true)
    expect(canAccess(u, "members")).toBe(false)
    expect(canAccess(u, "payments")).toBe(false)
  })

  it("owner sees all gym features but no platform features", () => {
    const u = makeUser("owner")
    expect(canAccess(u, "members")).toBe(true)
    expect(canAccess(u, "plans")).toBe(true)
    expect(canAccess(u, "payments")).toBe(true)
    expect(canAccess(u, "settings")).toBe(true)
    expect(canAccess(u, "tenants")).toBe(false)
  })

  it("staff sees dashboard + members + classes at baseline", () => {
    const u = makeUser("staff")
    expect(canAccess(u, "dashboard")).toBe(true)
    expect(canAccess(u, "members")).toBe(true)
    expect(canAccess(u, "classes")).toBe(true)
    // Payments — basic feature (not gated). Staff records walk-in
    // payments; refund button is hidden for them at the UI layer +
    // backend rejects for owner-only protection.
    expect(canAccess(u, "payments")).toBe(true)
    expect(canAccess(u, "settings")).toBe(false)
  })

  it("payments is basic — visible to owner / sales / staff regardless of tenantFeatures", () => {
    // Not gated, so empty tenantFeatures map shouldn't hide it.
    expect(canAccess(makeUser("owner"), "payments", undefined, {})).toBe(true)
    expect(canAccess(makeUser("sales"), "payments", undefined, {})).toBe(true)
    expect(canAccess(makeUser("staff"), "payments", undefined, {})).toBe(true)
    // Coach blocked.
    expect(canAccess(makeUser("coach"), "payments", undefined, {})).toBe(false)
    // super_admin baseline doesn't include payments — platform role.
    expect(canAccess(makeUser("super_admin"), "payments", undefined, {})).toBe(
      false,
    )
  })

  it("sales sees dashboard + members + classes at baseline", () => {
    const u = makeUser("sales")
    expect(canAccess(u, "dashboard")).toBe(true)
    expect(canAccess(u, "members")).toBe(true)
    expect(canAccess(u, "classes")).toBe(true)
    // Leads is in sales' baseline but gated — visibility requires the
    // tenant flag. With no flag map (default empty), it's hidden.
    expect(canAccess(u, "leads")).toBe(false)
    // With the flag enabled, sales sees leads.
    expect(canAccess(u, "leads", undefined, { leads: true })).toBe(true)
    expect(canAccess(u, "settings")).toBe(false)
  })

  it("null user has no access", () => {
    expect(canAccess(null, "dashboard")).toBe(false)
    expect(canAccess(undefined, "dashboard")).toBe(false)
  })

  it("coach sees dashboard + classes + attendance + coaches at baseline", () => {
    const u = makeUser("coach")
    // Coaches + schedule are gated — pass them as enabled for this test.
    const enabled = { coaches: true, schedule: true }
    expect(canAccess(u, "dashboard", undefined, enabled)).toBe(true)
    expect(canAccess(u, "classes", undefined, enabled)).toBe(true)
    expect(canAccess(u, "attendance", undefined, enabled)).toBe(true)
    expect(canAccess(u, "coaches", undefined, enabled)).toBe(true)
    expect(canAccess(u, "schedule", undefined, enabled)).toBe(true)
    // Owner-only / cross-feature items hidden from coach baseline.
    expect(canAccess(u, "members", undefined, enabled)).toBe(false)
    expect(canAccess(u, "plans", undefined, enabled)).toBe(false)
    expect(canAccess(u, "payments", undefined, enabled)).toBe(false)
    expect(canAccess(u, "settings", undefined, enabled)).toBe(false)
  })

  it("gated feature hidden when tenant flag off, even for owner", () => {
    const u = makeUser("owner")
    // Owner has coaches in baseline, but tenant flag is off.
    expect(canAccess(u, "coaches", undefined, {})).toBe(false)
    expect(canAccess(u, "coaches", undefined, { coaches: true })).toBe(true)
    // Schedule same.
    expect(canAccess(u, "schedule", undefined, {})).toBe(false)
    expect(canAccess(u, "schedule", undefined, { schedule: true })).toBe(true)
    // Leads same — owner does NOT see it without the tenant flag.
    expect(canAccess(u, "leads", undefined, {})).toBe(false)
    expect(canAccess(u, "leads", undefined, { leads: false })).toBe(false)
    expect(canAccess(u, "leads", undefined, { leads: true })).toBe(true)
    // Ungated members ignores tenantFeatures.
    expect(canAccess(u, "members", undefined, {})).toBe(true)
  })
})

describe("canAccess — tenant overrides", () => {
  const overrides: TenantOverrides = {
    staff: ["members", "payments"],
    sales: ["leads", "members"],
  }

  it("grants overridden features to staff", () => {
    const u = makeUser("staff")
    expect(canAccess(u, "members", overrides)).toBe(true)
    expect(canAccess(u, "payments", overrides)).toBe(true)
    expect(canAccess(u, "leads", overrides)).toBe(false)
  })

  it("grants overridden features to sales", () => {
    const u = makeUser("sales")
    // leads is gated — visibility needs the tenant flag too.
    expect(canAccess(u, "leads", overrides, { leads: true })).toBe(true)
    expect(canAccess(u, "members", overrides)).toBe(true)
    // payments is now in sales BASELINE — it's basic, not an override
    // grant. Sales sees it regardless of override config.
    expect(canAccess(u, "payments", overrides)).toBe(true)
  })

  it("does not apply staff overrides to sales or vice versa", () => {
    const staff = makeUser("staff")
    const sales = makeUser("sales")
    // staff has leads in BASELINE now (read-only access) but the gate
    // still blocks visibility without the tenant flag.
    expect(canAccess(staff, "leads", overrides)).toBe(false)
    // ``settings`` isn't in sales' baseline AND isn't in their
    // overrides — confirms the cross-role contamination guard works.
    expect(canAccess(sales, "settings", overrides)).toBe(false)
  })

  it("owner baseline is not affected by overrides", () => {
    const u = makeUser("owner")
    expect(canAccess(u, "members", overrides)).toBe(true)
    expect(canAccess(u, "settings", overrides)).toBe(true)
  })

  it("super_admin is not affected by overrides", () => {
    const u = makeUser("super_admin")
    expect(canAccess(u, "members", overrides)).toBe(false)
    expect(canAccess(u, "tenants", overrides)).toBe(true)
  })
})

describe("accessibleFeatures", () => {
  it("returns baseline for roles with no overrides", () => {
    // Staff baseline: front-desk + leads (read-only) + payments (record).
    // Leads is gated — accessibleFeatures filters it out when no
    // tenantFeatures map is supplied.
    expect(accessibleFeatures(makeUser("staff"))).toEqual([
      "dashboard",
      "members",
      "classes",
      "attendance",
      "payments",
    ])
    // Sales: pipeline + members + payments (records the convert flow's
    // first payment). No attendance — that's an operations task.
    expect(accessibleFeatures(makeUser("sales"))).toEqual([
      "dashboard",
      "members",
      "classes",
      "payments",
    ])
  })

  it("merges baseline and overrides for staff", () => {
    // Adding ``reports`` via the override on top of the baseline.
    const features = accessibleFeatures(makeUser("staff"), {
      staff: ["reports"],
      sales: [],
    })
    expect(features).toEqual([
      "dashboard",
      "members",
      "classes",
      "attendance",
      "payments",
      "reports",
    ])
  })

  it("owner always sees full gym feature set", () => {
    const features = accessibleFeatures(makeUser("owner"))
    expect(features).toContain("members")
    expect(features).toContain("settings")
    expect(features).not.toContain("tenants")
  })

  it("null user gets empty list", () => {
    expect(accessibleFeatures(null)).toEqual([])
  })
})

describe("GRANTABLE_FEATURES", () => {
  it("excludes owner-only and super_admin-only features", () => {
    expect(GRANTABLE_FEATURES).not.toContain("settings")
    expect(GRANTABLE_FEATURES).not.toContain("tenants")
    expect(GRANTABLE_FEATURES).not.toContain("dashboard")
  })

  it("includes the standard gym features an owner can delegate", () => {
    expect(GRANTABLE_FEATURES).toContain("members")
    expect(GRANTABLE_FEATURES).toContain("leads")
    expect(GRANTABLE_FEATURES).toContain("payments")
  })
})
