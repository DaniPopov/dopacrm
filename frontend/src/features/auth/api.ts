import { apiClient } from "@/lib/api-client"
import { ApiError } from "@/lib/api-errors"
import type { LoginRequest, TokenResponse, User } from "./types"

// Re-export for convenience so LoginPage can catch it.
// Keeps backwards compat with any test that imports LoginError.
export { ApiError as LoginError }

/**
 * Authenticate a user via email + password.
 *
 * Sends JSON to `POST /api/v1/auth/login` with `credentials: "include"` so
 * the browser stores the HttpOnly cookie set by the backend. Does NOT go
 * through `apiClient` because apiClient's 401 triggers auth-redirect logic —
 * for login, 401 is a normal "wrong credentials" error.
 *
 * @param data - `{ email, password }`
 * @returns `TokenResponse` with `access_token`, `token_type`, `expires_in`
 * @throws `ApiError(401)` — wrong email or password
 * @throws `ApiError(429)` — rate limited (10 attempts/min/IP)
 * @throws `ApiError(0)` — network failure (server unreachable)
 */
export async function login(data: LoginRequest): Promise<TokenResponse> {
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

/**
 * Fetch the current user's profile from the session cookie.
 *
 * `GET /api/v1/auth/me` — the browser sends the HttpOnly cookie automatically.
 * Called by `AuthProvider` on mount to restore the session.
 *
 * @returns The authenticated `User` object
 * @throws `ApiError(401)` — not authenticated (cookie missing or expired)
 */
export function getMe(): Promise<User> {
  return apiClient.get("/auth/me")
}

/**
 * Log out the current user.
 *
 * `POST /api/v1/auth/logout` — the backend clears the HttpOnly cookie and
 * blacklists the token's `jti` in Redis so it can't be reused.
 *
 * The caller (`AuthProvider.logout`) catches and ignores errors — even if the
 * server call fails, the frontend clears the user and navigates to `/login`.
 */
export function logout(): Promise<void> {
  return apiClient.post("/auth/logout")
}
