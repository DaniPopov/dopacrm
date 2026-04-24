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
    expect(canAccess(u, "payments")).toBe(false)
    expect(canAccess(u, "settings")).toBe(false)
  })

  it("sales sees dashboard + members + classes at baseline", () => {
    const u = makeUser("sales")
    expect(canAccess(u, "dashboard")).toBe(true)
    expect(canAccess(u, "members")).toBe(true)
    expect(canAccess(u, "classes")).toBe(true)
    expect(canAccess(u, "leads")).toBe(false)
    expect(canAccess(u, "settings")).toBe(false)
  })

  it("null user has no access", () => {
    expect(canAccess(null, "dashboard")).toBe(false)
    expect(canAccess(undefined, "dashboard")).toBe(false)
  })

  it("coach sees dashboard + classes + attendance + coaches at baseline", () => {
    const u = makeUser("coach")
    expect(canAccess(u, "dashboard")).toBe(true)
    expect(canAccess(u, "classes")).toBe(true)
    expect(canAccess(u, "attendance")).toBe(true)
    expect(canAccess(u, "coaches")).toBe(true)
    // Owner-only / cross-feature items hidden from coach baseline.
    expect(canAccess(u, "members")).toBe(false)
    expect(canAccess(u, "plans")).toBe(false)
    expect(canAccess(u, "payments")).toBe(false)
    expect(canAccess(u, "settings")).toBe(false)
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
    expect(canAccess(u, "leads", overrides)).toBe(true)
    expect(canAccess(u, "members", overrides)).toBe(true)
    expect(canAccess(u, "payments", overrides)).toBe(false)
  })

  it("does not apply staff overrides to sales or vice versa", () => {
    const staff = makeUser("staff")
    const sales = makeUser("sales")
    expect(canAccess(staff, "leads", overrides)).toBe(false)
    expect(canAccess(sales, "payments", overrides)).toBe(false)
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
    // Staff baseline includes attendance (front-desk check-in).
    expect(accessibleFeatures(makeUser("staff"))).toEqual([
      "dashboard",
      "members",
      "classes",
      "attendance",
    ])
    // Sales does NOT — check-in is an operations task.
    expect(accessibleFeatures(makeUser("sales"))).toEqual([
      "dashboard",
      "members",
      "classes",
    ])
  })

  it("merges baseline and overrides for staff", () => {
    const features = accessibleFeatures(makeUser("staff"), {
      staff: ["payments"],
      sales: [],
    })
    expect(features).toEqual([
      "dashboard",
      "members",
      "classes",
      "attendance",
      "payments",
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
