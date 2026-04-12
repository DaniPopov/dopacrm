# DopaCRM — Frontend Architecture

> Deep dive into the React/TypeScript frontend. For the product spec see [`spec.md`](./spec.md).

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
- **Invalidation after mutations** — create a tenant -> tenant list auto-refetches
- **Deduplication** — two components using `useTenants()` share one request
- **Retry on failure** — 3 retries by default
- **Tab refocus refetch** — data refreshes when the user returns to the tab

---

## Folder Structure

```
frontend/src/
├── app/                          # App shell
│   ├── App.tsx                   # Routes + page imports + guard wrappers
│   └── providers.tsx             # QueryClientProvider + BrowserRouter + AuthProvider
│
├── components/                   # Shared, reusable components
│   ├── ui/                       # shadcn/ui primitives (button, input, card, dialog, etc.)
│   └── layout/                   # App-level layout components
│       ├── DashboardLayout.tsx   # Shell: Sidebar + routed main content
│       ├── Sidebar.tsx           # Role-based nav via declarative NAV_ITEMS array
│       ├── ProtectedRoute.tsx    # Auth guard: logged in? no -> /login
│       └── RequireFeature.tsx    # Permission guard: canAccess? no -> /dashboard
│
├── features/                     # Feature modules (the core of the app)
│   ├── auth/
│   │   ├── api.ts                # login(), getMe(), logout()
│   │   ├── api.test.ts           # 7 tests
│   │   ├── auth-provider.tsx     # AuthContext + useAuth() hook
│   │   ├── LoginPage.tsx         # Login form with Hebrew error messages
│   │   ├── LoginPage.test.tsx    # 10 tests
│   │   ├── types.ts              # LoginRequest, TokenResponse, User, Role
│   │   ├── permissions.ts        # canAccess(), accessibleFeatures(), Feature type
│   │   └── permissions.test.ts   # 16 tests
│   │
│   ├── tenants/
│   │   ├── api.ts                # listTenants(), getTenant(), createTenant(), updateTenant(),
│   │   │                         # suspendTenant(), activateTenant(), cancelTenant(), uploadLogo()
│   │   ├── api.test.ts           # 5 tests
│   │   ├── hooks.ts              # useTenants(), useTenant(), useCreateTenant(), useUpdateTenant(),
│   │   │                         # useSuspendTenant(), useActivateTenant(), useCancelTenant(), useUploadLogo()
│   │   ├── types.ts              # Tenant, TenantStatus, CreateTenantRequest, UpdateTenantRequest, UploadResponse
│   │   ├── TenantListPage.tsx    # Full CRUD page: create card, table, row actions, edit dialog
│   │   ├── TenantListPage.test.tsx  # 12 tests
│   │   ├── TenantForm.tsx        # Shared form (create + edit)
│   │   └── ConfirmDialog.tsx     # Destructive action confirmation modal
│   │
│   ├── dashboard/
│   │   ├── DashboardPage.tsx     # Role dispatcher: super_admin -> Admin, else -> Gym
│   │   ├── AdminDashboard.tsx    # Hebrew platform metrics (tenants, users)
│   │   ├── GymDashboard.tsx      # Hebrew gym metrics (members, MRR, leads) + quick actions
│   │   └── StatCard.tsx          # Shared metric card widget
│   │
│   ├── users/
│   │   └── UserListPage.tsx      # Placeholder (to be built)
│   │
│   └── landing/
│       ├── LandingPage.tsx       # Hebrew landing page for gym CRM
│       └── LandingPage.test.tsx  # 6 tests
│
├── lib/                          # Utilities (not feature-specific)
│   ├── api-client.ts             # Fetch wrapper: cookie auth, error handling
│   ├── api-client.test.ts        # 6 tests
│   ├── api-errors.ts             # ApiError class + Hebrew humanizer functions
│   ├── api-errors.test.ts        # 15 tests
│   └── utils.ts                  # cn() helper for Tailwind class merging
│
├── test/
│   └── setup.ts                  # Vitest setup (jest-dom matchers)
│
├── index.css                     # Tailwind + global styles + Rubik font
└── main.tsx                      # Entry point
```

---

## Feature Module Pattern

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

No React, no hooks, no state. Just typed HTTP calls. Easy to test in isolation.

### hooks.ts — TanStack Query wrappers

Hooks handle caching, loading states, and invalidation. Pages consume them. Every mutation invalidates the relevant query key on success so lists auto-refresh.

### Page component — uses hooks

Pages are thin: call hooks, handle loading/error, render components. Errors go through humanizer functions from `lib/api-errors.ts`.

---

## API Reference

### `lib/api-client.ts` — HTTP client

Single point for all HTTP. Uses HttpOnly cookies (`credentials: "include"`) — no token management in JavaScript.

```ts
class ApiClient {
  /** Internal: executes fetch with JSON headers, cookie, and error handling.
   *  Network errors throw ApiError(status=0). 401 throws ApiError(401).
   *  204 returns undefined. All other non-ok responses throw ApiError(status). */
  private request<T>(method: string, path: string, body?: unknown): Promise<T>

  /** GET /api/v1{path} */
  get<T>(path: string): Promise<T>

  /** POST /api/v1{path} with optional JSON body */
  post<T>(path: string, body?: unknown): Promise<T>

  /** PATCH /api/v1{path} with optional JSON body */
  patch<T>(path: string, body?: unknown): Promise<T>

  /** DELETE /api/v1{path} */
  delete<T>(path: string): Promise<T>
}

export const apiClient: ApiClient  // Singleton, imported by all api.ts files
```

### `lib/api-errors.ts` — Error class + Hebrew humanizers

```ts
/** Error carrying the HTTP status code (0 = network failure). */
export class ApiError extends Error {
  constructor(message: string, public readonly status: number)
}

/** Generic Hebrew fallback table.
 *  0 -> "אין חיבור לשרת..."  |  401 -> "נדרשת התחברות מחדש"
 *  403 -> "אין לכם הרשאה..."  |  404 -> "הפריט לא נמצא"
 *  409 -> "הפריט כבר קיים"    |  429 -> "יותר מדי בקשות..."
 *  500+ -> "שגיאת מערכת..."    |  other -> "אירעה שגיאה, נסו שוב" */
function genericMessage(status: number): string

/** Login errors. 401 -> "שגיאה במייל או סיסמה",
 *  403 -> "החשבון מושהה...", 429 -> "יותר מדי ניסיונות..." */
export function humanizeLoginError(err: unknown): string

/** Tenant CRUD errors. 409 -> "מזהה URL (slug) כבר תפוס",
 *  422 -> "הפרטים שהוזנו אינם תקינים..." */
export function humanizeTenantError(err: unknown): string

/** Upload errors. 413 -> "הלוגו גדול מדי (מקסימום 2MB)",
 *  415 -> "סוג הקובץ אינו נתמך (PNG, JPG, WebP או SVG)" */
export function humanizeUploadError(err: unknown): string
```

### `features/auth/api.ts` — Auth functions

```ts
/** POST /api/v1/auth/login — JSON body {email, password}.
 *  Backend sets HttpOnly cookie. Returns TokenResponse.
 *  Does NOT go through apiClient — login 401 should be a normal error,
 *  not an auth-redirect.
 *  @throws ApiError(401) wrong credentials
 *  @throws ApiError(429) rate limited (10/min/IP)
 *  @throws ApiError(0) network failure */
export function login(data: LoginRequest): Promise<TokenResponse>

/** GET /api/v1/auth/me — returns current user profile from cookie.
 *  @throws ApiError(401) not authenticated */
export function getMe(): Promise<User>

/** POST /api/v1/auth/logout — clears cookie + blacklists token in Redis.
 *  @throws ApiError on failure (caller ignores — logout continues anyway) */
export function logout(): Promise<void>
```

### `features/auth/types.ts` — Auth types

```ts
export type Role = "super_admin" | "owner" | "staff" | "sales"
export const ALL_GYM_ROLES: Role[]  // ["owner", "staff", "sales"]

export interface LoginRequest { email: string; password: string }
export interface TokenResponse { access_token: string; token_type: string; expires_in: number }
export interface User {
  id: string; email: string; role: Role; tenant_id: string | null
  is_active: boolean; oauth_provider: string | null
  created_at: string; updated_at: string
}
```

### `features/auth/permissions.ts` — Central permissions module

```ts
/** Every permission-gated feature in the app. Add new ones here as you build them. */
export type Feature =
  | "dashboard"
  | "tenants" | "platform_users"
  | "members" | "plans" | "leads" | "payments" | "reports" | "settings"

/** Features an owner can grant to staff/sales (excludes settings, platform features). */
export const GRANTABLE_FEATURES: Feature[]

/** Per-tenant overrides — what the owner has granted to each employee role.
 *  Placeholder shape. In the real system this becomes the role row itself. */
export interface TenantOverrides { staff: Feature[]; sales: Feature[] }

/** Does this user have access to this feature?
 *  Checks baseline role->feature map, then tenant overrides for staff/sales.
 *  Owner and super_admin always use the baseline (never overridden). */
export function canAccess(user: User | null | undefined, feature: Feature, overrides?: TenantOverrides): boolean

/** All features a user can see. Handy for building nav menus. */
export function accessibleFeatures(user: User | null | undefined, overrides?: TenantOverrides): Feature[]
```

### `features/auth/auth-provider.tsx` — Auth context

```ts
/** Context value provided by AuthProvider. */
interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: () => Promise<void>   // Refetch user after login() succeeds
  logout: () => Promise<void>  // POST /logout, clear user, navigate to /login
}

/** Wraps the app. On mount calls getMe() via cookie. */
export function AuthProvider({ children }: { children: ReactNode }): JSX.Element

/** Hook: access user, auth state, login/logout actions from anywhere. */
export function useAuth(): AuthContextValue
```

### `features/tenants/api.ts` — Tenant functions

```ts
/** GET /api/v1/tenants — list all tenants (super_admin only).
 *  @throws ApiError(403) not super_admin */
export function listTenants(): Promise<Tenant[]>

/** GET /api/v1/tenants/{id} — get tenant by ID (includes logo_presigned_url).
 *  @throws ApiError(404) not found */
export function getTenant(id: string): Promise<Tenant>

/** POST /api/v1/tenants — onboard a new gym.
 *  Auto-assigns default SaaS plan, status=trial, trial_ends_at=now+14d.
 *  @throws ApiError(409) slug already taken
 *  @throws ApiError(422) validation error */
export function createTenant(data: CreateTenantRequest): Promise<Tenant>

/** PATCH /api/v1/tenants/{id} — partial update of tenant fields.
 *  @throws ApiError(404) not found
 *  @throws ApiError(409) slug conflict */
export function updateTenant(id: string, data: UpdateTenantRequest): Promise<Tenant>

/** POST /api/v1/tenants/{id}/suspend — suspend a tenant.
 *  @throws ApiError(404) not found */
export function suspendTenant(id: string): Promise<Tenant>

/** POST /api/v1/tenants/{id}/activate — reactivate a suspended/trial/cancelled tenant.
 *  @throws ApiError(404) not found */
export function activateTenant(id: string): Promise<Tenant>

/** POST /api/v1/tenants/{id}/cancel — soft-delete (status=cancelled). Reversible via activate.
 *  @throws ApiError(404) not found */
export function cancelTenant(id: string): Promise<Tenant>

/** POST /api/v1/uploads/logo — multipart file upload to S3.
 *  Returns { key, presigned_url } for immediate preview.
 *  Does NOT go through apiClient (multipart, not JSON).
 *  @throws Error(413) file too large
 *  @throws Error(415) unsupported type */
export function uploadLogo(file: File): Promise<UploadResponse>
```

### `features/tenants/hooks.ts` — Tenant TanStack Query hooks

```ts
/** Fetch all tenants. Query key: ["tenants"]. */
export function useTenants(): UseQueryResult<Tenant[]>

/** Fetch one tenant by ID. Query key: ["tenants", id]. Disabled when id is empty. */
export function useTenant(id: string): UseQueryResult<Tenant>

/** Create a tenant. Invalidates ["tenants"] on success. */
export function useCreateTenant(): UseMutationResult<Tenant, Error, CreateTenantRequest>

/** Update a tenant. Invalidates ["tenants"] on success. */
export function useUpdateTenant(): UseMutationResult<Tenant, Error, { id: string; data: UpdateTenantRequest }>

/** Suspend a tenant. Invalidates ["tenants"] on success. */
export function useSuspendTenant(): UseMutationResult<Tenant, Error, string>

/** Activate a tenant. Invalidates ["tenants"] on success. */
export function useActivateTenant(): UseMutationResult<Tenant, Error, string>

/** Cancel a tenant. Invalidates ["tenants"] on success. */
export function useCancelTenant(): UseMutationResult<Tenant, Error, string>

/** Upload a logo file. Returns { key, presigned_url }. */
export function useUploadLogo(): UseMutationResult<UploadResponse, Error, File>
```

### `features/tenants/types.ts` — Tenant types

```ts
export type TenantStatus = "trial" | "active" | "suspended" | "cancelled"

export interface Tenant {
  id: string; slug: string; name: string; status: TenantStatus
  saas_plan_id: string
  logo_url: string | null; logo_presigned_url: string | null
  phone: string | null; email: string | null; website: string | null
  address_street: string | null; address_city: string | null
  address_country: string | null; address_postal_code: string | null
  legal_name: string | null; tax_id: string | null
  timezone: string; currency: string; locale: string
  trial_ends_at: string | null; created_at: string; updated_at: string
}

export interface CreateTenantRequest {
  slug: string; name: string
  logo_url?: string | null; phone?: string | null; email?: string | null; website?: string | null
  address_street?: string | null; address_city?: string | null
  address_country?: string | null; address_postal_code?: string | null
  legal_name?: string | null; tax_id?: string | null
  timezone?: string; currency?: string; locale?: string
}

export interface UpdateTenantRequest { /* same as Create but all fields optional */ }
export interface UploadResponse { key: string; presigned_url: string }
```

---

## Auth Flow

1. **Login** — `POST /auth/login` (JSON body) -> backend sets HttpOnly cookie. Frontend calls `refreshAuth()` to fetch user via `getMe()`.
2. **AuthProvider** — wraps the app. On mount, calls `GET /auth/me` (cookie sent by browser). Provides `useAuth()` hook: `{ user, isAuthenticated, isLoading, login, logout }`.
3. **ProtectedRoute** — redirects to `/login` if `isAuthenticated` is false.
4. **API client** — `credentials: "include"` sends cookie automatically. No token handling in JS.
5. **Logout** — `POST /auth/logout` -> backend blacklists token in Redis + clears cookie. Frontend sets `user = null`, navigates to `/login`.
6. **Security** — token stored in HttpOnly cookie (XSS-immune). Redis blacklist prevents reuse after logout. No `localStorage` anywhere.

---

## Routing

```typescript
// app/App.tsx
<Route path="/" element={<LandingPage />} />        {/* Hebrew landing */}
<Route path="/login" element={<LoginPage />} />
<Route element={<ProtectedRoute />}>                 {/* checks auth */}
  <Route element={<DashboardLayout />}>              {/* sidebar + outlet */}
    <Route path="/dashboard" element={<DashboardPage />} />

    {/* Permission-gated routes — typing the URL doesn't bypass the sidebar */}
    <Route element={<RequireFeature feature="tenants" />}>
      <Route path="/tenants" element={<TenantListPage />} />
    </Route>
    <Route element={<RequireFeature feature="platform_users" />}>
      <Route path="/users" element={<UserListPage />} />
    </Route>
  </Route>
</Route>
```

**Two guard layers:**
- `ProtectedRoute` — is the user logged in? No -> redirect to `/login`
- `RequireFeature` — does the user have access to this feature? No -> redirect to `/dashboard`

---

## Permissions (role-based feature visibility)

The golden rule: **never write `user.role === "..."` in a component.** Always go through `canAccess(user, feature)`.

### Why this matters

Hardcoding role checks in 50 components means that the day you add a new role (or make roles owner-configurable — see `docs/features/roles.md`), you're hunting through the codebase. Centralizing in one module means you change one file.

### The module

`features/auth/permissions.ts` is the single source of truth.

Internally it holds a `BASELINE: Record<Role, Feature[]>` dict that maps each role to its allowed features. **This is a placeholder** — when the dynamic roles system lands (see `docs/features/roles.md`), `canAccess` collapses to `user?.role.features.includes(feature)` and the dict goes away. Call sites don't change.

### Using it — sidebar

```tsx
// components/layout/Sidebar.tsx
const NAV_ITEMS = [
  { to: "/dashboard", label: "דשבורד", icon: "📊", feature: "dashboard" },
  { to: "/tenants",   label: "חדרי כושר", icon: "🏢", feature: "tenants" },
  { to: "/users",     label: "משתמשים",  icon: "👤", feature: "platform_users" },
]

const visibleItems = NAV_ITEMS.filter((item) => canAccess(user, item.feature))
```

Adding a link = one array entry. No inline conditionals, no role checks.

### Using it — route guard

```tsx
// components/layout/RequireFeature.tsx
export default function RequireFeature({ feature }: { feature: Feature }) {
  const { user } = useAuth()
  if (!canAccess(user, feature)) return <Navigate to="/dashboard" replace />
  return <Outlet />
}
```

### Role-based page dispatch (the dashboard pattern)

`/dashboard` is one route that dispatches to different components:

- **super_admin** sees `AdminDashboard` — platform metrics: total tenants, users, new gyms
- **owner/staff/sales** sees `GymDashboard` — gym metrics: active members, MRR, leads, quick actions

Both share the `StatCard` widget. All values show "בקרוב" until backend metrics land.

*(The `user.role === "super_admin"` check in DashboardPage is the single intentional exception — it's a layout decision, not a permission check.)*

---

## Testing

**Tool:** Vitest + Testing Library + jsdom

**Pattern:** tests live next to the code they test.

**Current test count:** 77 tests across 8 files

| File | Tests | What it covers |
|------|-------|----------------|
| `features/auth/permissions.test.ts` | 16 | canAccess baseline per role, tenant overrides, accessibleFeatures, GRANTABLE_FEATURES |
| `lib/api-errors.test.ts` | 15 | ApiError class, humanizeLoginError, humanizeTenantError, humanizeUploadError |
| `features/tenants/TenantListPage.test.tsx` | 12 | Renders table, create form, row actions, suspend/activate/cancel flows |
| `features/auth/LoginPage.test.tsx` | 10 | Render, validation, success redirect, error states, loading |
| `features/auth/api.test.ts` | 7 | login(), getMe(), logout(), error cases |
| `lib/api-client.test.ts` | 6 | Cookie auth, 401 handling, 204, error parsing |
| `features/landing/LandingPage.test.tsx` | 6 | Hebrew content, feature cards, navigation |
| `features/tenants/api.test.ts` | 5 | list, get, create, update, suspend |

**Run:** `make test-frontend` or `cd frontend && npx vitest run`

---

## Conventions

- **One feature, one folder.** Pages, hooks, API, types, and tests — all co-located.
- **api.ts is pure.** No React imports, no hooks. Just typed fetch calls.
- **hooks.ts wraps api.ts.** TanStack Query handles caching/invalidation.
- **Pages are thin.** Call hooks, handle loading/error, render components.
- **Errors go through humanizers.** Every page catches `ApiError` and calls a `humanize*Error` function from `lib/api-errors.ts`. Never show raw backend `detail` to users.
- **Shared forms.** Create + Edit use the same form component (`TenantForm`), passed different `initial` props and `submitLabel`.
- **Row actions.** Tables use a "פעולות" dropdown menu per row, with conditionally-shown items based on status. Destructive actions (Cancel/Delete) open a `ConfirmDialog`.
- **Modal dialogs.** Use fixed-positioned overlays with backdrop click to close. Edit uses a scrollable dialog that reuses the form component.
- **Static images in `public/`.** Referenced as URL strings (`"/dopa-icon.png"`). No module imports.
- **Tests live next to code.** `Foo.tsx` -> `Foo.test.tsx`, `api.ts` -> `api.test.ts`.
- **Shared components in `components/`.** Feature-specific components in the feature folder.
- **Types mirror backend schemas.** Eventually auto-generated from OpenAPI.
- **No prop drilling for auth.** Use `useAuth()` hook from anywhere.
- **Permissions via canAccess().** Never inline `user.role === "..."`. See permissions section above.

---

## Related docs

- [`spec.md`](./spec.md) — product specification
- [`backend.md`](./backend.md) — backend architecture (what the frontend talks to)
- [`features/auth.md`](./features/auth.md) — auth feature doc
- [`features/roles.md`](./features/roles.md) — dynamic roles system (planned)
- [`skills/build-frontend-feature.md`](./skills/build-frontend-feature.md) — step-by-step recipe for a new frontend feature
- [`skills/build-backend-feature.md`](./skills/build-backend-feature.md) — step-by-step recipe for a new backend feature
