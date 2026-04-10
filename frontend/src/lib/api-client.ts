/**
 * Centralized API client.
 *
 * Uses HttpOnly cookies for auth — the browser sends the cookie
 * automatically. No token management in JavaScript.
 *
 * `credentials: "include"` tells fetch to send cookies on every request.
 */

const API_BASE = "/api/v1"

class ApiClient {
  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" }

    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "include",
      body: body ? JSON.stringify(body) : undefined,
    })

    if (res.status === 401) {
      // Don't redirect for auth-check calls — let the caller handle it
      throw new Error("Unauthorized")
    }

    if (res.status === 204) {
      return undefined as T
    }

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(
        typeof data.detail === "string" ? data.detail : `Request failed: ${res.status}`,
      )
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
