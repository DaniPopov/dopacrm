import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  cancelMember,
  createMember,
  freezeMember,
  getMember,
  listMembers,
  unfreezeMember,
  updateMember,
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

describe("members/api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("listMembers: no filters hits GET /members", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listMembers()
    expect(mocks.get).toHaveBeenCalledWith("/members")
  })

  it("listMembers: passes status (repeated) + search + pagination as query string", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listMembers({
      status: ["active", "frozen"],
      search: "dana",
      limit: 20,
      offset: 40,
    })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("status=active")
    expect(path).toContain("status=frozen")
    expect(path).toContain("search=dana")
    expect(path).toContain("limit=20")
    expect(path).toContain("offset=40")
  })

  it("getMember hits GET /members/:id", async () => {
    mocks.get.mockResolvedValueOnce({})
    await getMember("abc-123")
    expect(mocks.get).toHaveBeenCalledWith("/members/abc-123")
  })

  it("createMember posts the body", async () => {
    mocks.post.mockResolvedValueOnce({})
    const body = { first_name: "Dana", last_name: "Cohen", phone: "+972-50-1", custom_fields: {} }
    await createMember(body as never)
    expect(mocks.post).toHaveBeenCalledWith("/members", body)
  })

  it("updateMember patches /members/:id with the body", async () => {
    mocks.patch.mockResolvedValueOnce({})
    await updateMember("m1", { notes: "hi" } as never)
    expect(mocks.patch).toHaveBeenCalledWith("/members/m1", { notes: "hi" })
  })

  it("freezeMember posts { until } — undefined becomes null", async () => {
    mocks.post.mockResolvedValueOnce({})
    await freezeMember("m1")
    expect(mocks.post).toHaveBeenCalledWith("/members/m1/freeze", { until: null })
  })

  it("freezeMember passes an explicit until date", async () => {
    mocks.post.mockResolvedValueOnce({})
    await freezeMember("m1", "2026-05-12")
    expect(mocks.post).toHaveBeenCalledWith("/members/m1/freeze", { until: "2026-05-12" })
  })

  it("unfreezeMember posts to /members/:id/unfreeze", async () => {
    mocks.post.mockResolvedValueOnce({})
    await unfreezeMember("m1")
    expect(mocks.post).toHaveBeenCalledWith("/members/m1/unfreeze")
  })

  it("cancelMember posts to /members/:id/cancel", async () => {
    mocks.post.mockResolvedValueOnce({})
    await cancelMember("m1")
    expect(mocks.post).toHaveBeenCalledWith("/members/m1/cancel")
  })
})
