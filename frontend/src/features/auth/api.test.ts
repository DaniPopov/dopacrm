import { describe, it, expect, vi, beforeEach } from "vitest"

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

import { getMe, logout } from "./api"

beforeEach(() => {
  vi.clearAllMocks()
})

describe("auth api", () => {
  it("getMe calls GET /auth/me", async () => {
    mockGet.mockResolvedValue({ id: "1", email: "admin@test.com", role: "super_admin" })
    const result = await getMe()
    expect(mockGet).toHaveBeenCalledWith("/auth/me")
    expect(result.email).toBe("admin@test.com")
  })

  it("logout calls POST /auth/logout", async () => {
    mockPost.mockResolvedValue(undefined)
    await logout()
    expect(mockPost).toHaveBeenCalledWith("/auth/logout")
  })
})

describe("login", () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch)
    mockFetch.mockReset()
  })

  it("sends JSON to /api/v1/auth/login with credentials: include", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ access_token: "jwt", token_type: "bearer", expires_in: 28800 }),
    })

    const { login } = await import("./api")
    const result = await login({ email: "a@b.com", password: "pass" })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ email: "a@b.com", password: "pass" }),
      }),
    )
    expect(result.access_token).toBe("jwt")
  })

  it("throws LoginError with status 401 on wrong credentials", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Invalid credentials" }),
    })

    const { login, LoginError } = await import("./api")
    try {
      await login({ email: "a@b.com", password: "wrong" })
      throw new Error("should have thrown")
    } catch (err) {
      expect(err).toBeInstanceOf(LoginError)
      expect((err as InstanceType<typeof LoginError>).status).toBe(401)
    }
  })

  it("throws LoginError with status 429 on rate limit", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      json: () => Promise.resolve({ detail: "Rate limit exceeded. Try again in 45s." }),
    })

    const { login, LoginError } = await import("./api")
    try {
      await login({ email: "a@b.com", password: "pass" })
      throw new Error("should have thrown")
    } catch (err) {
      expect(err).toBeInstanceOf(LoginError)
      expect((err as InstanceType<typeof LoginError>).status).toBe(429)
    }
  })

  it("throws LoginError with status 500 on server error", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.resolve({}),
    })

    const { login, LoginError } = await import("./api")
    try {
      await login({ email: "a@b.com", password: "pass" })
      throw new Error("should have thrown")
    } catch (err) {
      expect(err).toBeInstanceOf(LoginError)
      expect((err as InstanceType<typeof LoginError>).status).toBe(500)
    }
  })

  it("throws LoginError with status 0 on network failure", async () => {
    mockFetch.mockRejectedValue(new TypeError("Failed to fetch"))

    const { login, LoginError } = await import("./api")
    try {
      await login({ email: "a@b.com", password: "pass" })
      throw new Error("should have thrown")
    } catch (err) {
      expect(err).toBeInstanceOf(LoginError)
      expect((err as InstanceType<typeof LoginError>).status).toBe(0)
    }
  })
})
