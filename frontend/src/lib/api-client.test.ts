import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// We test the ApiClient behavior by mocking fetch
const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

// Must import after mocking fetch
const { apiClient } = await import("./api-client")

beforeEach(() => {
  mockFetch.mockReset()
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe("ApiClient", () => {
  it("sends GET request with auth header when token exists", async () => {
    localStorage.setItem("token", "test-jwt-token")
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
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-token",
        }),
      }),
    )
    expect(result).toEqual([{ id: "1", name: "Test" }])
  })

  it("sends request without auth header when no token", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    await apiClient.get("/test")

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })

  it("sends POST with JSON body", async () => {
    localStorage.setItem("token", "jwt")
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

  it("clears token and redirects on 401", async () => {
    localStorage.setItem("token", "expired-token")
    // Mock window.location
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
    expect(localStorage.getItem("token")).toBeNull()
  })

  it("handles 204 No Content (logout)", async () => {
    localStorage.setItem("token", "jwt")
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
    })

    const result = await apiClient.post("/auth/logout")
    expect(result).toBeUndefined()
  })
})
