import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  activatePlan,
  createPlan,
  deactivatePlan,
  getPlan,
  listPlans,
  updatePlan,
} from "./api"
import { apiClient } from "@/lib/api-client"

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mocks = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

describe("plans/api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("listPlans: no options → plain GET /plans", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listPlans()
    expect(mocks.get).toHaveBeenCalledWith("/plans")
  })

  it("listPlans: includeInactive sets the query flag", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listPlans({ includeInactive: true })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("include_inactive=true")
  })

  it("listPlans: passes pagination", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listPlans({ limit: 20, offset: 40 })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("limit=20")
    expect(path).toContain("offset=40")
  })

  it("getPlan hits /plans/:id", async () => {
    mocks.get.mockResolvedValueOnce({})
    await getPlan("p1")
    expect(mocks.get).toHaveBeenCalledWith("/plans/p1")
  })

  it("createPlan posts the body (incl. entitlements)", async () => {
    mocks.post.mockResolvedValueOnce({})
    const body = {
      name: "חודשי",
      type: "recurring",
      price_cents: 45000,
      currency: "ILS",
      billing_period: "monthly",
      entitlements: [{ class_id: null, quantity: 3, reset_period: "weekly" }],
    }
    await createPlan(body as never)
    expect(mocks.post).toHaveBeenCalledWith("/plans", body)
  })

  it("updatePlan patches /plans/:id", async () => {
    mocks.patch.mockResolvedValueOnce({})
    await updatePlan("p1", { price_cents: 50000 } as never)
    expect(mocks.patch).toHaveBeenCalledWith("/plans/p1", { price_cents: 50000 })
  })

  it("deactivatePlan posts to /plans/:id/deactivate", async () => {
    mocks.post.mockResolvedValueOnce({})
    await deactivatePlan("p1")
    expect(mocks.post).toHaveBeenCalledWith("/plans/p1/deactivate")
  })

  it("activatePlan posts to /plans/:id/activate", async () => {
    mocks.post.mockResolvedValueOnce({})
    await activatePlan("p1")
    expect(mocks.post).toHaveBeenCalledWith("/plans/p1/activate")
  })
})
