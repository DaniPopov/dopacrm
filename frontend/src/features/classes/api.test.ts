import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  activateClass,
  createClass,
  deactivateClass,
  getClass,
  listClasses,
  updateClass,
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

describe("classes/api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("listClasses: no options → plain GET /classes", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listClasses()
    expect(mocks.get).toHaveBeenCalledWith("/classes")
  })

  it("listClasses: includeInactive sets the query flag", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listClasses({ includeInactive: true })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("include_inactive=true")
  })

  it("listClasses: passes pagination", async () => {
    mocks.get.mockResolvedValueOnce([])
    await listClasses({ limit: 20, offset: 40 })
    const [path] = mocks.get.mock.calls[0]
    expect(path).toContain("limit=20")
    expect(path).toContain("offset=40")
  })

  it("getClass hits /classes/:id", async () => {
    mocks.get.mockResolvedValueOnce({})
    await getClass("c1")
    expect(mocks.get).toHaveBeenCalledWith("/classes/c1")
  })

  it("createClass posts the body", async () => {
    mocks.post.mockResolvedValueOnce({})
    const body = { name: "Yoga", color: "#10B981", description: "relaxing" }
    await createClass(body as never)
    expect(mocks.post).toHaveBeenCalledWith("/classes", body)
  })

  it("updateClass patches /classes/:id", async () => {
    mocks.patch.mockResolvedValueOnce({})
    await updateClass("c1", { color: "#FF0000" } as never)
    expect(mocks.patch).toHaveBeenCalledWith("/classes/c1", { color: "#FF0000" })
  })

  it("deactivateClass posts to /classes/:id/deactivate", async () => {
    mocks.post.mockResolvedValueOnce({})
    await deactivateClass("c1")
    expect(mocks.post).toHaveBeenCalledWith("/classes/c1/deactivate")
  })

  it("activateClass posts to /classes/:id/activate", async () => {
    mocks.post.mockResolvedValueOnce({})
    await activateClass("c1")
    expect(mocks.post).toHaveBeenCalledWith("/classes/c1/activate")
  })
})
