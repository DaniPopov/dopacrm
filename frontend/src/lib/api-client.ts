const API_BASE = "/api/v1"

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem("token")
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    const token = this.getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`

    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })

    if (res.status === 401) {
      localStorage.removeItem("token")
      window.location.href = "/login"
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
