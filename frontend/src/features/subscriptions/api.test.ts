import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  cancelSubscription,
  changePlan,
  createSubscription,
  freezeSubscription,
  getSubscription,
  listSubscriptionEvents,
  listSubscriptions,
  renewSubscription,
  unfreezeSubscription,
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

describe("subscriptions/api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("listSubscriptions: no options → plain GET /subscriptions", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listSubscriptions()
    expect(mocks.get).toHaveBeenCalledWith("/subscriptions")
  })

  it("listSubscriptions: filters flow into query string", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listSubscriptions({
      memberId: "m1",
      status: "active",
      planId: "p1",
      expiresBefore: "2026-05-01",
      expiresWithinDays: 7,
      limit: 20,
      offset: 40,
    })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("member_id=m1")
    expect(path).toContain("status=active")
    expect(path).toContain("plan_id=p1")
    expect(path).toContain("expires_before=2026-05-01")
    expect(path).toContain("expires_within_days=7")
    expect(path).toContain("limit=20")
    expect(path).toContain("offset=40")
  })

  it("getSubscription hits /subscriptions/:id", async () => {
    mocks.get.mockResolvedValueOnce({})
    await getSubscription("s1")
    expect(mocks.get).toHaveBeenCalledWith("/subscriptions/s1")
  })

  it("listSubscriptionEvents hits /subscriptions/:id/events", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listSubscriptionEvents("s1")
    expect(mocks.get).toHaveBeenCalledWith("/subscriptions/s1/events")
  })

  it("createSubscription posts the body", async () => {
    mocks.post.mockResolvedValueOnce({})
    const body = { member_id: "m1", plan_id: "p1", started_at: null, expires_at: null }
    await createSubscription(body as never)
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions", body)
  })

  it("freezeSubscription posts to /subscriptions/:id/freeze with body", async () => {
    mocks.post.mockResolvedValueOnce({})
    await freezeSubscription("s1", { frozen_until: "2026-05-01" })
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions/s1/freeze", {
      frozen_until: "2026-05-01",
    })
  })

  it("unfreezeSubscription posts to /subscriptions/:id/unfreeze (no body)", async () => {
    mocks.post.mockResolvedValueOnce({})
    await unfreezeSubscription("s1")
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions/s1/unfreeze")
  })

  it("renewSubscription posts to /subscriptions/:id/renew with body", async () => {
    mocks.post.mockResolvedValueOnce({})
    await renewSubscription("s1", { new_expires_at: "2026-06-01" })
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions/s1/renew", {
      new_expires_at: "2026-06-01",
    })
  })

  it("changePlan posts to /subscriptions/:id/change-plan with body", async () => {
    mocks.post.mockResolvedValueOnce({})
    await changePlan("s1", { new_plan_id: "p2", effective_date: null })
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions/s1/change-plan", {
      new_plan_id: "p2",
      effective_date: null,
    })
  })

  it("cancelSubscription posts to /subscriptions/:id/cancel with body", async () => {
    mocks.post.mockResolvedValueOnce({})
    await cancelSubscription("s1", { reason: "moved_away", detail: null })
    expect(mocks.post).toHaveBeenCalledWith("/subscriptions/s1/cancel", {
      reason: "moved_away",
      detail: null,
    })
  })
})
