import { apiClient } from "@/lib/api-client"
import type { LoginRequest, TokenResponse, User } from "./types"

export async function login(data: LoginRequest): Promise<TokenResponse> {
  // Login uses credentials: "include" so the HttpOnly cookie is set by the browser.
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === "string" ? body.detail : "Invalid credentials",
    )
  }

  return res.json()
}

export function getMe(): Promise<User> {
  return apiClient.get("/auth/me")
}

export function logout(): Promise<void> {
  return apiClient.post("/auth/logout")
}
