import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { apiClient } from "@/lib/api-client"
import {
  getPayment,
  getRevenueSummary,
  listMemberPayments,
  listPayments,
  recordPayment,
  refundPayment,
} from "./api"

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const get = apiClient.get as ReturnType<typeof vi.fn>
const post = apiClient.post as ReturnType<typeof vi.fn>

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  get.mockResolvedValue({})
  post.mockResolvedValue({})
})
afterEach(() => {
  vi.clearAllMocks()
})

describe("payments/api", () => {
  it("listPayments with no filters hits /payments", async () => {
    await listPayments()
    expect(get).toHaveBeenCalledWith("/payments")
  })

  it("listPayments serializes filters into the query string", async () => {
    await listPayments({
      memberId: "m1",
      paidFrom: "2026-04-01",
      paidTo: "2026-04-30",
      method: "cash",
      includeRefunds: false,
      limit: 50,
    })
    const url = get.mock.calls[0][0] as string
    expect(url).toContain("member_id=m1")
    expect(url).toContain("paid_from=2026-04-01")
    expect(url).toContain("paid_to=2026-04-30")
    expect(url).toContain("method=cash")
    expect(url).toContain("include_refunds=false")
    expect(url).toContain("limit=50")
  })

  it("recordPayment posts to /payments with body", async () => {
    await recordPayment({
      member_id: "m1",
      amount_cents: 25000,
      payment_method: "cash",
      paid_at: "2026-04-30",
      subscription_id: null,
      notes: null,
      external_ref: null,
      backdate: false,
    })
    expect(post).toHaveBeenCalledWith(
      "/payments",
      expect.objectContaining({ amount_cents: 25000 }),
    )
  })

  it("refundPayment posts to /payments/:id/refund", async () => {
    await refundPayment("p1", { amount_cents: 10000, reason: "test" })
    expect(post).toHaveBeenCalledWith(
      "/payments/p1/refund",
      expect.objectContaining({ amount_cents: 10000 }),
    )
  })

  it("getPayment hits /payments/:id", async () => {
    await getPayment("p1")
    expect(get).toHaveBeenCalledWith("/payments/p1")
  })

  it("listMemberPayments hits /members/:id/payments", async () => {
    await listMemberPayments("m1")
    expect(get).toHaveBeenCalledWith("/members/m1/payments")
  })

  it("getRevenueSummary hits /dashboard/revenue", async () => {
    await getRevenueSummary()
    expect(get).toHaveBeenCalledWith("/dashboard/revenue")
  })
})
