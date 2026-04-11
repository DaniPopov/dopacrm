import { apiClient } from "@/lib/api-client"
import { ApiError } from "@/lib/api-errors"
import type { LoginRequest, TokenResponse, User } from "./types"

// Re-export for convenience so LoginPage can catch it.
// Keeps backwards compat with any test that imports LoginError.
export { ApiError as LoginError }

export async function login(data: LoginRequest): Promise<TokenResponse> {
  // Login uses credentials: "include" so the HttpOnly cookie is set by the browser.
  // We don't go through apiClient here because apiClient's 401 is special for
  // auth-check flows — for login, 401 should be treated as a normal error.
  let res: Response
  try {
    res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    })
  } catch {
    throw new ApiError("network", 0)
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === "string" ? body.detail : res.statusText
    throw new ApiError(detail, res.status)
  }

  return res.json()
}

export function getMe(): Promise<User> {
  return apiClient.get("/auth/me")
}

export function logout(): Promise<void> {
  return apiClient.post("/auth/logout")
}
