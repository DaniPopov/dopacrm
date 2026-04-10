import { describe, it, expect, vi, beforeEach } from "vitest"

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}))

import { listTenants, getTenant, createTenant, updateTenant, suspendTenant } from "./api"

beforeEach(() => {
  vi.clearAllMocks()
})

describe("tenants api", () => {
  it("listTenants calls GET /tenants", async () => {
    mockGet.mockResolvedValue([{ id: "1", slug: "gym-a" }])
    const result = await listTenants()
    expect(mockGet).toHaveBeenCalledWith("/tenants")
    expect(result).toEqual([{ id: "1", slug: "gym-a" }])
  })

  it("getTenant calls GET /tenants/:id", async () => {
    mockGet.mockResolvedValue({ id: "abc", slug: "gym-a" })
    const result = await getTenant("abc")
    expect(mockGet).toHaveBeenCalledWith("/tenants/abc")
    expect(result.id).toBe("abc")
  })

  it("createTenant calls POST /tenants with body", async () => {
    const payload = { slug: "new-gym", name: "New Gym" }
    mockPost.mockResolvedValue({ id: "new", ...payload })
    const result = await createTenant(payload)
    expect(mockPost).toHaveBeenCalledWith("/tenants", payload)
    expect(result.slug).toBe("new-gym")
  })

  it("updateTenant calls PATCH /tenants/:id with body", async () => {
    mockPatch.mockResolvedValue({ id: "abc", name: "Updated" })
    const result = await updateTenant("abc", { name: "Updated" })
    expect(mockPatch).toHaveBeenCalledWith("/tenants/abc", { name: "Updated" })
    expect(result.name).toBe("Updated")
  })

  it("suspendTenant calls POST /tenants/:id/suspend", async () => {
    mockPost.mockResolvedValue({ id: "abc", status: "suspended" })
    const result = await suspendTenant("abc")
    expect(mockPost).toHaveBeenCalledWith("/tenants/abc/suspend")
    expect(result.status).toBe("suspended")
  })
})
