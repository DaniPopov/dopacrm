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
| HTTP | Typed fetch wrapper (`lib/api-client.ts`) |
| Testing | Vitest + Testing Library |

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
│   ├── App.tsx                   # Routes + page imports
│   └── providers.tsx             # QueryClientProvider + BrowserRouter + AuthProvider
│
├── components/                   # Shared, reusable components
│   ├── ui/                       # shadcn/ui primitives (button, input, card, label)
│   └── layout/                   # ProtectedRoute, DashboardLayout (header + logout)
│
├── features/                     # Feature modules (the core of the app)
│   ├── auth/
│   │   ├── api.ts                # login(), getMe(), logout()
│   │   ├── api.test.ts           # Tests for API functions
│   │   ├── auth-provider.tsx     # AuthContext + useAuth() hook
│   │   ├── LoginPage.tsx         # Login form
│   │   ├── LoginPage.test.tsx    # Tests for login page
│   │   └── types.ts              # LoginRequest, TokenResponse, User
│   │
│   ├── tenants/
│   │   ├── api.ts                # listTenants(), createTenant(), updateTenant(), suspendTenant()
│   │   ├── api.test.ts           # Tests for API functions
│   │   ├── hooks.ts              # useTenants(), useCreateTenant(), useSuspendTenant()
│   │   └── types.ts              # Tenant, CreateTenantRequest, UpdateTenantRequest
│   │   # Pages (TenantListPage, TenantForm, etc.) — to be built
│   │
│   ├── landing/
│   │   ├── LandingPage.tsx       # Hebrew landing page for gym CRM
│   │   └── LandingPage.test.tsx  # Tests for landing page
│   │
│   ├── dashboard/
│   │   └── DashboardPage.tsx     # Widget grid (placeholders for now)
│   │
│   ├── users/                    # (future)
│   ├── members/                  # (future)
│   ├── plans/                    # (future)
│   └── leads/                    # (future)
│
├── lib/                          # Utilities (not feature-specific)
│   ├── api-client.ts             # Fetch wrapper: base URL, auth headers, error handling
│   ├── api-client.test.ts        # Tests for API client
│   └── utils.ts                  # cn() helper for Tailwind class merging
│
├── test/
│   └── setup.ts                  # Vitest setup (jest-dom matchers)
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

`lib/api-client.ts` is the single point for all HTTP communication. Uses HttpOnly cookies — **no token handling in JavaScript**.

```typescript
const API_BASE = "/api/v1"

class ApiClient {
  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" }

    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "include",  // sends HttpOnly cookie automatically
      body: body ? JSON.stringify(body) : undefined,
    })

    if (res.status === 401) throw new Error("Unauthorized")
    if (res.status === 204) return undefined as T

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(
        typeof data.detail === "string" ? data.detail : `Request failed: ${res.status}`,
      )
    }

    return res.json()
  }

  get<T>(path: string): Promise<T>                    { return this.request("GET", path) }
  post<T>(path: string, body?: unknown): Promise<T>   { return this.request("POST", path, body) }
  patch<T>(path: string, body?: unknown): Promise<T>  { return this.request("PATCH", path, body) }
  delete<T>(path: string): Promise<T>                 { return this.request("DELETE", path) }
}

export const apiClient = new ApiClient()
```

Key points:
- `credentials: "include"` tells the browser to send the HttpOnly cookie on every request
- No `localStorage`, no token injection, no `Authorization` header in the frontend
- 401 throws an error — `ProtectedRoute` handles the redirect to `/login`
- The backend sets/clears the cookie; JavaScript never touches it

---

## Auth flow

1. **Login** — `POST /auth/login` → backend sets HttpOnly cookie. Frontend calls `refreshAuth()` to fetch user.
2. **AuthProvider** — wraps the app. On mount, calls `GET /auth/me` (cookie sent by browser). Provides `useAuth()` hook: `{ user, isAuthenticated, isLoading, login, logout }`.
3. **ProtectedRoute** — redirects to `/login` if `isAuthenticated` is false.
4. **API client** — `credentials: "include"` sends cookie automatically. No token handling in JS.
5. **Logout** — `POST /auth/logout` → backend blacklists token in Redis + clears cookie. Frontend sets `user = null`, navigates to `/login`.
6. **Security** — token stored in HttpOnly cookie (XSS-immune). Redis blacklist prevents reuse after logout. No `localStorage` anywhere.

---

## Routing

```typescript
// app/App.tsx
<Route path="/" element={<LandingPage />} />        {/* Hebrew landing */}
<Route path="/login" element={<LoginPage />} />
<Route element={<ProtectedRoute />}>                 {/* checks auth */}
  <Route element={<DashboardLayout />}>              {/* header + logout */}
    <Route path="/dashboard" element={<DashboardPage />} />
    {/* Future:
    <Route path="/tenants" element={<TenantListPage />} />
    <Route path="/users" element={<UserListPage />} />
    <Route path="/members" element={<MemberListPage />} />
    <Route path="/leads" element={<LeadListPage />} />
    */}
  </Route>
</Route>
```

---

## Testing

**Tool:** Vitest + Testing Library + jsdom

**Pattern:** tests live next to the code they test.

```
features/auth/
├── api.ts
├── api.test.ts          ← tests the API functions
├── LoginPage.tsx
└── LoginPage.test.tsx   ← tests the page component
```

**What to test per feature:**
- `api.test.ts` — correct endpoints called, request body shape, error handling
- `*.test.tsx` — renders correctly, user interactions work, navigation on success/error

**Current test count:** 25 tests across 5 files

| File | Tests | What it covers |
|------|-------|----------------|
| `lib/api-client.test.ts` | 7 | Auth header injection, 401 redirect, 204, error parsing |
| `features/auth/api.test.ts` | 4 | login(), getMe(), logout(), login error |
| `features/auth/LoginPage.test.tsx` | 4 | Render, success, error, loading state |
| `features/tenants/api.test.ts` | 5 | list, get, create, update, suspend |
| `features/landing/LandingPage.test.tsx` | 5 | Hebrew content, cards, navigation |

**Run:** `make test-frontend` or `cd frontend && npx vitest run`

---

## Conventions

- **One feature, one folder.** Pages, hooks, API, types, and tests — all co-located.
- **api.ts is pure.** No React imports, no hooks. Just typed fetch calls.
- **hooks.ts wraps api.ts.** TanStack Query handles caching/invalidation.
- **Pages are thin.** Call hooks, handle loading/error, render components.
- **Tests live next to code.** `Foo.tsx` → `Foo.test.tsx`, `api.ts` → `api.test.ts`.
- **Shared components in `components/`.** Feature-specific components in the feature folder.
- **Types mirror backend schemas.** Eventually auto-generated from OpenAPI.
- **No prop drilling for auth.** Use `useAuth()` hook from anywhere.

---

## Related docs

- [`specs.md`](./specs.md) — product specification (§7 Frontend Stack)
- [`backend.md`](./backend.md) — backend architecture (what the frontend talks to)
- [`features/auth.md`](./features/auth.md) — auth feature doc (backend + frontend)
