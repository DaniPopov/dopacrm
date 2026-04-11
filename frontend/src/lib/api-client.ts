/**
 * Centralized API client.
 *
 * Uses HttpOnly cookies for auth — the browser sends the cookie
 * automatically. No token management in JavaScript.
 *
 * `credentials: "include"` tells fetch to send cookies on every request.
 *
 * All failures throw ``ApiError`` with a ``status`` field so callers can
 * localize error messages (see ``lib/api-errors.ts``).
 */

import { ApiError } from "./api-errors"

const API_BASE = "/api/v1"

class ApiClient {
  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" }

    let res: Response
    try {
      res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        credentials: "include",
        body: body ? JSON.stringify(body) : undefined,
      })
    } catch {
      // Network error (browser couldn't reach the server at all)
      throw new ApiError("network", 0)
    }

    if (res.status === 204) return undefined as T

    if (res.status === 401) {
      // Don't redirect here — let ProtectedRoute + AuthProvider handle it.
      throw new ApiError("Unauthorized", 401)
    }

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const detail =
        typeof data.detail === "string" ? data.detail : `Request failed: ${res.status}`
      throw new ApiError(detail, res.status)
    }

    return res.json()
  }

  get<T>(path: string): Promise<T> {
    return this.request("GET", path)
  }
  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request("POST", path, body)
  }
  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request("PATCH", path, body)
  }
  delete<T>(path: string): Promise<T> {
    return this.request("DELETE", path)
  }
}

export const apiClient = new ApiClient()
