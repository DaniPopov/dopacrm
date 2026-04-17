import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  listEntries,
  listMemberEntries,
  memberSummary,
  quotaCheck,
  recordEntry,
  undoEntry,
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
}

describe("attendance/api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("quotaCheck builds the two-param query string", async () => {
    mocks.get.mockResolvedValueOnce({})
    await quotaCheck({ memberId: "m1", classId: "c1" })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("/attendance/quota-check")
    expect(path).toContain("member_id=m1")
    expect(path).toContain("class_id=c1")
  })

  it("recordEntry POSTs to /attendance with the body", async () => {
    mocks.post.mockResolvedValueOnce({})
    const body = { member_id: "m1", class_id: "c1", override: false, override_reason: null }
    await recordEntry(body as never)
    expect(mocks.post).toHaveBeenCalledWith("/attendance", body)
  })

  it("undoEntry POSTs to /attendance/:id/undo", async () => {
    mocks.post.mockResolvedValueOnce({})
    await undoEntry("e1", { reason: "wrong member" } as never)
    expect(mocks.post).toHaveBeenCalledWith("/attendance/e1/undo", {
      reason: "wrong member",
    })
  })

  it("listEntries without filters hits plain /attendance", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listEntries()
    expect(mocks.get).toHaveBeenCalledWith("/attendance")
  })

  it("listEntries pipes every filter into the query string", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listEntries({
      memberId: "m1",
      classId: "c1",
      dateFrom: "2026-04-01T00:00:00Z",
      dateTo: "2026-04-30T00:00:00Z",
      includeUndone: true,
      undoneOnly: false,
      overrideOnly: true,
      limit: 20,
      offset: 10,
    })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("member_id=m1")
    expect(path).toContain("class_id=c1")
    expect(path).toContain("date_from=")
    expect(path).toContain("date_to=")
    expect(path).toContain("include_undone=true")
    expect(path).toContain("override_only=true")
    expect(path).toContain("limit=20")
    expect(path).toContain("offset=10")
    expect(path).not.toContain("undone_only=true") // false was skipped
  })

  it("listMemberEntries builds the right URL", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listMemberEntries("m1", 25)
    expect(mocks.get).toHaveBeenCalledWith("/attendance/members/m1?limit=25")
  })

  it("memberSummary hits /attendance/members/:id/summary", async () => {
    mocks.get.mockResolvedValueOnce([])
    await memberSummary("m1")
    expect(mocks.get).toHaveBeenCalledWith("/attendance/members/m1/summary")
  })
})
