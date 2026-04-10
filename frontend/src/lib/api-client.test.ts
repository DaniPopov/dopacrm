import { describe, it, expect, vi, beforeEach } from "vitest"

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

const { apiClient } = await import("./api-client")

beforeEach(() => {
  mockFetch.mockReset()
})

describe("ApiClient", () => {
  it("sends GET request with credentials: include", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve([{ id: "1", name: "Test" }]),
    })

    const result = await apiClient.get("/tenants")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/tenants",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
      }),
    )
    expect(result).toEqual([{ id: "1", name: "Test" }])
  })

  it("sends POST with JSON body and credentials", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 201,
      json: () => Promise.resolve({ id: "new" }),
    })

    await apiClient.post("/tenants", { slug: "gym", name: "Gym" })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/tenants",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ slug: "gym", name: "Gym" }),
      }),
    )
  })

  it("throws error with detail message on non-ok response", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ detail: "Slug already taken" }),
    })

    await expect(apiClient.post("/tenants", {})).rejects.toThrow("Slug already taken")
  })

  it("throws generic error when detail is not a string", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: [{ msg: "field required" }] }),
    })

    await expect(apiClient.post("/tenants", {})).rejects.toThrow("Request failed: 422")
  })

  it("redirects to login on 401", async () => {
    const originalHref = window.location.href
    Object.defineProperty(window, "location", {
      value: { href: originalHref },
      writable: true,
    })

    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Token expired" }),
    })

    await expect(apiClient.get("/me")).rejects.toThrow("Unauthorized")
  })

  it("handles 204 No Content (logout)", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
    })

    const result = await apiClient.post("/auth/logout")
    expect(result).toBeUndefined()
  })
})
