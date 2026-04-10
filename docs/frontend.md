# DopaCRM — Frontend Architecture

> Deep dive into the React/TypeScript frontend. For the product spec see [`specs.md`](./specs.md).

---

## Stack

| Component | Technology |
|-----------|-----------|
| Language | TypeScript (strict) |
| Framework | React 19 |
| Build | Vite |
| Routing | React Router |
| Server state | TanStack Query (React Query) |
| UI components | shadcn/ui (Tailwind CSS) |
| HTTP | Typed fetch wrapper (generated from OpenAPI in the future) |

---

## Why TanStack Query

We use TanStack Query for all server-state management. It replaces manual `useState` + `useEffect` + `fetch` patterns with declarative hooks that handle:

- **Loading / error / data states** — built in, no boilerplate
- **Caching** — navigate away and back, data is instant from cache
- **Background refetching** — stale data shows immediately, fresh data replaces it
- **Invalidation after mutations** — create a tenant → tenant list auto-refetches
- **Deduplication** — two components using `useTenants()` share one request
- **Retry on failure** — 3 retries by default
- **Tab refocus refetch** — data refreshes when the user returns to the tab

---

## Folder Structure

```
frontend/src/
├── app/                          # App shell
│   ├── App.tsx                   # Router + providers
│   ├── routes.tsx                # Route definitions (lazy-loaded)
│   └── providers.tsx             # QueryClientProvider, AuthProvider
│
├── components/                   # Shared, reusable components
│   ├── ui/                       # shadcn/ui primitives (button, input, card, table, etc.)
│   └── layout/                   # Shell: Sidebar, TopBar, PageHeader, ProtectedRoute
│
├── features/                     # Feature modules (the core of the app)
│   ├── auth/
│   │   ├── api.ts                # login(), getMe()
│   │   ├── hooks.ts              # useAuth(), useLogin()
│   │   ├── auth-provider.tsx     # AuthContext + token management
│   │   ├── LoginPage.tsx         # Login form
│   │   └── types.ts              # LoginRequest, TokenResponse, User
│   │
│   ├── tenants/
│   │   ├── api.ts                # listTenants(), createTenant(), updateTenant(), suspendTenant()
│   │   ├── hooks.ts              # useTenants(), useCreateTenant(), useSuspendTenant()
│   │   ├── TenantListPage.tsx    # Table of all gyms (super_admin)
│   │   ├── TenantForm.tsx        # Create / edit form
│   │   ├── TenantDetail.tsx      # Single tenant view
│   │   └── types.ts              # Tenant, CreateTenantRequest, UpdateTenantRequest
│   │
│   ├── users/
│   │   ├── api.ts
│   │   ├── hooks.ts
│   │   ├── UserListPage.tsx
│   │   └── types.ts
│   │
│   ├── members/                  # (future)
│   ├── plans/                    # (future)
│   ├── leads/                    # (future)
│   │
│   └── dashboard/
│       ├── api.ts                # fetchDashboardMetrics()
│       ├── hooks.ts              # useDashboardMetrics()
│       ├── DashboardPage.tsx     # Widget grid
│       └── widgets/              # MRR card, member count, churn chart, etc.
│
├── lib/                          # Utilities (not feature-specific)
│   ├── api-client.ts             # Fetch wrapper: base URL, auth headers, error handling
│   ├── utils.ts                  # cn() helper for Tailwind class merging
│   └── constants.ts              # API_BASE_URL, etc.
│
├── hooks/                        # Shared hooks (not feature-specific)
│
├── index.css                     # Tailwind + global styles
└── main.tsx                      # Entry point
```

---

## Feature module pattern

Every feature follows the same structure:

```
features/<name>/
├── api.ts          # Pure fetch functions — no React, no hooks
├── hooks.ts        # TanStack Query hooks wrapping api.ts
├── types.ts        # TypeScript types matching backend schemas
├── <Name>Page.tsx  # Page component (connected to router)
└── <Name>*.tsx     # Feature-specific components (forms, tables, etc.)
```

### api.ts — pure fetch functions

```typescript
// features/tenants/api.ts
import { apiClient } from "@/lib/api-client"
import type { Tenant, CreateTenantRequest } from "./types"

export function listTenants(): Promise<Tenant[]> {
  return apiClient.get("/tenants")
}

export function createTenant(data: CreateTenantRequest): Promise<Tenant> {
  return apiClient.post("/tenants", data)
}

export function suspendTenant(id: string): Promise<Tenant> {
  return apiClient.post(`/tenants/${id}/suspend`)
}
```

No React, no hooks, no state. Just typed HTTP calls. Easy to test in isolation.

### hooks.ts — TanStack Query wrappers

```typescript
// features/tenants/hooks.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { listTenants, createTenant, suspendTenant } from "./api"
import type { CreateTenantRequest } from "./types"

export function useTenants() {
  return useQuery({
    queryKey: ["tenants"],
    queryFn: listTenants,
  })
}

export function useCreateTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTenantRequest) => createTenant(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}

export function useSuspendTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => suspendTenant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenants"] }),
  })
}
```

Hooks handle caching, loading states, and invalidation. Pages consume them.

### Page component — uses hooks

```typescript
// features/tenants/TenantListPage.tsx
export default function TenantListPage() {
  const { data: tenants, isLoading, error } = useTenants()
  const suspend = useSuspendTenant()

  if (isLoading) return <Spinner />
  if (error) return <ErrorMessage error={error} />

  return (
    <table>
      {tenants?.map((t) => (
        <tr key={t.id}>
          <td>{t.name}</td>
          <td>{t.status}</td>
          <td>
            <Button onClick={() => suspend.mutate(t.id)}>
              {suspend.isPending ? "..." : "Suspend"}
            </Button>
          </td>
        </tr>
      ))}
    </table>
  )
}
```

---

## API client

`lib/api-client.ts` is the single point for all HTTP communication:

```typescript
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

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail ?? `Request failed: ${res.status}`)
    }

    return res.json()
  }

  get<T>(path: string): Promise<T>          { return this.request("GET", path) }
  post<T>(path: string, body?: unknown): Promise<T>  { return this.request("POST", path, body) }
  patch<T>(path: string, body?: unknown): Promise<T>  { return this.request("PATCH", path, body) }
  delete<T>(path: string): Promise<T>       { return this.request("DELETE", path) }
}

export const apiClient = new ApiClient()
```

All features go through this. Token injection, 401 redirect, error parsing — one place.

---

## Auth flow

1. **Login** — `POST /auth/login` → store JWT in `localStorage`
2. **AuthProvider** — wraps the app, provides `useAuth()` hook with `user`, `isAuthenticated`, `logout()`
3. **ProtectedRoute** — layout component that redirects to `/login` if not authenticated
4. **API client** — reads token from `localStorage`, injects as `Bearer` header
5. **401 handling** — API client clears token and redirects to login

---

## Routing

```typescript
// app/routes.tsx
<Route path="/login" element={<LoginPage />} />
<Route element={<ProtectedRoute />}>        {/* checks auth */}
  <Route element={<DashboardLayout />}>     {/* sidebar + topbar */}
    <Route path="/dashboard" element={<DashboardPage />} />
    <Route path="/tenants" element={<TenantListPage />} />
    <Route path="/tenants/:id" element={<TenantDetail />} />
    <Route path="/users" element={<UserListPage />} />
    <Route path="/members" element={<MemberListPage />} />
    <Route path="/leads" element={<LeadListPage />} />
  </Route>
</Route>
```

---

## Conventions

- **One feature, one folder.** Pages, hooks, API, types — all co-located.
- **api.ts is pure.** No React imports, no hooks. Just typed fetch calls.
- **hooks.ts wraps api.ts.** TanStack Query handles caching/invalidation.
- **Pages are thin.** Call hooks, handle loading/error, render components.
- **Shared components in `components/`.** Feature-specific components in the feature folder.
- **Types mirror backend schemas.** Eventually auto-generated from OpenAPI.
- **No prop drilling for auth.** Use `useAuth()` hook from anywhere.

---

## Related docs

- [`specs.md`](./specs.md) — product specification (§7 Frontend Stack)
- [`backend.md`](./backend.md) — backend architecture (what the frontend talks to)
