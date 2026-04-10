# Feature: Auth

## Summary

Email + password authentication for the dashboard. Returns a JWT access
token that authenticates all subsequent API requests. Logout endpoint
clears the session. super_admin users can log in without a tenant scope.
OAuth (Google/Microsoft) is planned for Phase 2 — the database schema
supports it but no routes exist yet.

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | `/api/v1/auth/login` | None | 10/min/IP | Email + password → JWT access token |
| POST | `/api/v1/auth/logout` | Bearer | 60/min/user | Invalidate session (client-side token removal) |
| GET | `/api/v1/auth/me` | Bearer | 60/min/user | Current user profile from token |

## Domain (Layer 3)

### Entities

- **`domain/entities/user.py`** — `User` + `Role` enum (shared with Users feature)

### Exceptions

- `InvalidCredentialsError` → 401 (wrong email or password)

## Service (Layer 2)

Auth orchestration currently lives inline in the route handler (no
separate auth_service.py). When refresh tokens are added, create
`services/auth_service.py` with:

- `login(email, password, tenant_id)` → validate credentials, return token pair
- `refresh(refresh_token)` → validate, rotate, return new access token
- `logout(refresh_token)` → revoke token in DB + add access token to Redis blacklist

## Adapter (Layer 4)

### Repository methods used

- `UserRepository.find_with_credentials(email, tenant_id)` — returns
  `(User, password_hash)` tuple. The hash leaves the repo here but the
  route verifies and discards it immediately.

### Security utilities

File: `core/security.py`

- `hash_password(plain) → str` — argon2id hash
- `verify_password(plain, hashed) → bool` — constant-time comparison
- `create_access_token(user_id, role, tenant_id, secret_key) → str` — HS256 JWT, 8h expiry
- `decode_access_token(token, secret_key) → TokenPayload` — decodes + validates
- `TokenPayload` — Pydantic model: sub (user ID), role, tenant_id, type

### JWT details

| Field | Value |
|-------|-------|
| Algorithm | HS256 |
| Signing key | `APP_SECRET_KEY` (min 32 chars, SecretStr) |
| Access token expiry | 8 hours |
| Payload fields | sub (user UUID), role, tenant_id, type ("access"), iat, exp |

## API (Layer 1)

### Routes

File: `api/v1/auth/router.py`

- **POST `/login`** — accepts JSON `{email, password}`. Looks up user by
  email (tries super_admin first, then any tenant user). Verifies password
  with argon2. Returns `{access_token, token_type, expires_in}`.
- **POST `/logout`** — requires valid Bearer token. Returns 204. Currently
  client-side only (frontend removes the token from localStorage). When
  refresh tokens are implemented, this will revoke them server-side and
  add the access token to a Redis blacklist.
- **GET `/me`** — decodes JWT from `Authorization: Bearer` header, fetches
  user from DB, returns `UserResponse`.

### Schemas

File: `api/v1/auth/schemas.py`

**LoginRequest:**
```json
{
  "email": "dani@dopamineo.com",
  "password": "your-password"
}
```

**TokenResponse:**
```json
{
  "access_token": "<jwt-token>",
  "token_type": "bearer",
  "expires_in": 28800
}
```

### Dependencies

- `api/dependencies/auth.py`:
  - `bearer_scheme` — `HTTPBearer(auto_error=False)`, extracts token from header (fallback)
  - `get_current_user` — reads HttpOnly cookie first, falls back to Bearer header. Decodes JWT → `TokenPayload`. Checks Redis blacklist. Raises 401 on invalid/expired/revoked.
  - `require_role(*roles)` — checks `TokenPayload.role` against allowed roles
  - Shortcuts: `require_super_admin`, `require_owner`, `require_staff`

### Token storage & security

- **HttpOnly cookie** — JWT stored in an HttpOnly cookie (`access_token`), not in `localStorage`. JavaScript cannot read it → immune to XSS token theft.
- **Cookie settings:** `HttpOnly=true`, `SameSite=Lax`, `Secure=true` (prod only), `Path=/`
- **Dual auth support** — cookie (frontend) + Bearer header (Swagger, API clients, mobile). Cookie is checked first.
- **Redis blacklist** — on logout, the token's `jti` is stored in Redis with TTL = remaining expiry. Every auth check queries Redis. Fail-open if Redis is down.

### Token blacklist flow

```
Login → JWT created with jti (uuid) → HttpOnly cookie + response body
   ↓
Every request → read cookie/header → decode JWT → check Redis blacklist → allow/deny
   ↓
Logout → jti stored in Redis (TTL = remaining expiry) → cookie cleared
   ↓
Same token reused → Redis says blacklisted → 401 "Token has been revoked"
```

### Rate limiting

- `/login` → `login_rate_limit` (10 requests/min per IP) — brute-force protection
- `/logout`, `/me` → standard API rate limit (60/min per user)

## Frontend

### Auth flow

1. **Landing** (`/`) → user clicks "כניסה לפורטל"
2. **Login** (`/login`) → `features/auth/LoginPage.tsx` → calls `features/auth/api.ts → login()`
3. On success → browser stores HttpOnly cookie (set by backend), `AuthProvider.login()` refetches user
4. **AuthProvider** (`features/auth/auth-provider.tsx`) wraps the app:
   - On mount: calls `getMe()` (cookie sent automatically by browser)
   - Provides `useAuth()` hook: `{ user, isAuthenticated, isLoading, login, logout }`
5. **ProtectedRoute** (`components/layout/ProtectedRoute.tsx`) — redirects to `/login` if not authenticated
6. **Logout** — calls `POST /auth/logout` (blacklists token in Redis + clears cookie), redirects to `/login`
7. **API client** (`lib/api-client.ts`) — `credentials: "include"` sends cookie automatically. No token handling in JavaScript.

### Files

| File | Purpose |
|------|---------|
| `features/auth/api.ts` | `login()`, `getMe()`, `logout()` — pure fetch functions |
| `features/auth/types.ts` | `LoginRequest`, `TokenResponse`, `User` |
| `features/auth/auth-provider.tsx` | `AuthProvider` + `useAuth()` hook |
| `features/auth/LoginPage.tsx` | Login form page |
| `lib/api-client.ts` | Shared fetch wrapper (token injection, 401 handling) |
| `components/layout/ProtectedRoute.tsx` | Auth guard for routes |
| `components/layout/DashboardLayout.tsx` | Header with logout button |

## Tests

### Backend

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_security.py` | argon2 hash format, uniqueness, verify match/mismatch, needs_rehash |
| E2E | `tests/e2e/test_auth.py` | login success, wrong password, nonexistent email, /me, logout (valid/invalid/no token), SQL injection |

- Unit: 5 tests
- E2E: 14 tests
- **Backend total: 19 auth tests**

### Frontend

| File | What it covers |
|------|----------------|
| `features/auth/api.test.ts` | login() sends credentials:include, getMe(), logout(), error handling |
| `features/auth/LoginPage.test.tsx` | Renders form, success calls refreshAuth + navigates, failure shows error, loading state |

- Frontend total: 8 auth tests

### Security tests

| Test | What it proves |
|------|---------------|
| Login sets HttpOnly cookie | Cookie present in response |
| /me works via cookie | Full frontend auth flow |
| Token rejected after logout | Redis blacklist works — 401 "Token has been revoked" |
| SQL injection in email | Rejected (401/422), no 500 |
| SQL injection in password | 401, no auth bypass |
| UNION SELECT injection | Rejected, no data leak |
| Logout without token | 401/403, rejected |
| Logout with invalid token | 401, rejected |
| Tampered JWT (wrong signature) | 401 |
| Forged role escalation (wrong key) | 401 |
| Sales creating user (super_admin only) | 403 |
| Staff deleting user (owner+ only) | 403 |
| Owner with null tenant_id listing users | 403, not all users |

## Decisions

- **HttpOnly cookie over localStorage** — `localStorage` is vulnerable to XSS
  (any injected script can steal the token). HttpOnly cookies can't be read by
  JavaScript. The browser sends them automatically — no token management in JS.

- **Dual auth (cookie + header)** — the frontend uses cookies, but Swagger and
  API clients use Bearer headers. The auth dependency checks both, cookie first.

- **Redis blacklist over "just clear the cookie"** — clearing the cookie only
  works if the attacker didn't copy the token first. The Redis blacklist ensures
  the token is actually dead server-side. Fail-open if Redis is down.

- **HS256 over RS256** — single service, no need for asymmetric keys.

- **8-hour access token** — balances security with UX. Refresh tokens (30-day)
  are planned but not implemented yet.

- **TanStack Query not used for auth** — auth state is managed via
  `AuthProvider` context because it needs to be available before any
  queries run. TanStack Query is used for everything else (tenants, members, etc.).

## Swagger

1. Open http://localhost:8000/docs
2. **POST `/api/v1/auth/login`** → enter email + password → Execute
3. Copy the `access_token` from the response
4. Click **Authorize** (lock icon, top-right) → paste token → Authorize
5. **POST `/api/v1/auth/logout`** → Execute → 204
6. All protected endpoints now work with "Try it out"

## Planned (Phase 2)

- **Refresh tokens** — POST `/api/v1/auth/refresh` with refresh token → new access token + rotation
- **Google OAuth** — redirect flow → callback → JWT
- **Microsoft OAuth** — same pattern
- **Password reset** — email link → reset form → update hash
