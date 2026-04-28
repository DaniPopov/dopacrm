import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  addActivity,
  assignLead,
  convertLead,
  createLead,
  getLeadStats,
  listActivities,
  listLeads,
  listLostReasons,
  setLeadStatus,
} from "./api"
import { apiClient } from "@/lib/api-client"

// Mock the underlying client so each test asserts URL + body shape only.
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

describe("leads/api", () => {
  it("listLeads with no filters hits /leads", async () => {
    await listLeads()
    expect(get).toHaveBeenCalledWith("/leads")
  })

  it("listLeads serializes status, source, search into query string", async () => {
    await listLeads({
      status: ["new", "contacted"],
      source: ["walk_in"],
      search: "yael",
      limit: 50,
    })
    const url = get.mock.calls[0][0] as string
    expect(url).toContain("status=new")
    expect(url).toContain("status=contacted")
    expect(url).toContain("source=walk_in")
    expect(url).toContain("search=yael")
    expect(url).toContain("limit=50")
  })

  it("createLead posts to /leads with body", async () => {
    await createLead({
      first_name: "A",
      last_name: "B",
      phone: "+1",
    })
    expect(post).toHaveBeenCalledWith("/leads", expect.objectContaining({ phone: "+1" }))
  })

  it("setLeadStatus posts to /leads/:id/status", async () => {
    await setLeadStatus("abc", { new_status: "contacted", lost_reason: null })
    expect(post).toHaveBeenCalledWith(
      "/leads/abc/status",
      expect.objectContaining({ new_status: "contacted" }),
    )
  })

  it("assignLead posts to /leads/:id/assign with user_id payload", async () => {
    await assignLead("abc", { user_id: "user-1" })
    expect(post).toHaveBeenCalledWith(
      "/leads/abc/assign",
      expect.objectContaining({ user_id: "user-1" }),
    )
  })

  it("convertLead posts to /leads/:id/convert with the plan/payment payload", async () => {
    await convertLead("abc", {
      plan_id: "plan-1",
      payment_method: "cash",
      start_date: "2026-04-27",
      copy_notes_to_member: true,
    })
    expect(post).toHaveBeenCalledWith(
      "/leads/abc/convert",
      expect.objectContaining({ plan_id: "plan-1", payment_method: "cash" }),
    )
  })

  it("listActivities hits /leads/:id/activities", async () => {
    await listActivities("abc")
    expect(get).toHaveBeenCalledWith("/leads/abc/activities")
  })

  it("addActivity posts to /leads/:id/activities", async () => {
    await addActivity("abc", { type: "note", note: "hi" })
    expect(post).toHaveBeenCalledWith(
      "/leads/abc/activities",
      expect.objectContaining({ type: "note", note: "hi" }),
    )
  })

  it("getLeadStats hits /leads/stats", async () => {
    await getLeadStats()
    expect(get).toHaveBeenCalledWith("/leads/stats")
  })

  it("listLostReasons hits /leads/lost-reasons with optional days/limit", async () => {
    await listLostReasons({ days: 30, limit: 5 })
    const url = get.mock.calls[0][0] as string
    expect(url).toContain("/leads/lost-reasons")
    expect(url).toContain("days=30")
    expect(url).toContain("limit=5")
  })
})
