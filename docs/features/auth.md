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
  - `bearer_scheme` — `HTTPBearer(auto_error=True)`, extracts token from header
  - `get_current_user` — decodes JWT → `TokenPayload`, raises 401 on invalid/expired
  - `require_role(*roles)` — checks `TokenPayload.role` against allowed roles
  - Shortcuts: `require_super_admin`, `require_owner`, `require_staff`

### Rate limiting

- `/login` → `login_rate_limit` (10 requests/min per IP) — brute-force protection
- `/logout`, `/me` → standard API rate limit (60/min per user)

## Frontend

### Auth flow

1. **Landing** (`/`) → user clicks "כניסה לפורטל"
2. **Login** (`/login`) → `features/auth/LoginPage.tsx` → calls `features/auth/api.ts → login()`
3. On success → stores JWT in `localStorage`, navigates to `/dashboard`
4. **AuthProvider** (`features/auth/auth-provider.tsx`) wraps the app:
   - On mount: reads token from `localStorage`, calls `getMe()` to validate
   - Provides `useAuth()` hook: `{ user, isAuthenticated, isLoading, logout }`
5. **ProtectedRoute** (`components/layout/ProtectedRoute.tsx`) — redirects to `/login` if not authenticated
6. **Logout** — calls `POST /auth/logout`, clears `localStorage`, redirects to `/login`
7. **API client** (`lib/api-client.ts`) — auto-injects Bearer token, auto-redirects to `/login` on 401

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
- E2E: 11 tests
- **Backend total: 16 auth tests**

### Frontend

| File | What it covers |
|------|----------------|
| `features/auth/api.test.ts` | login(), getMe(), logout() — correct endpoints + error handling |
| `features/auth/LoginPage.test.tsx` | Renders form, success stores token + navigates, failure shows error, loading state |

- Frontend total: 8 auth tests

### Security tests

| Test | What it proves |
|------|---------------|
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
| API client 401 → clears token + redirects | Frontend test |

## Decisions

- **JWT over session cookies** — the dashboard is a React SPA. SPAs work
  better with Bearer tokens (no CSRF issues, works across origins).

- **HS256 over RS256** — single service, no need for asymmetric keys.
  Switch to RS256 if/when multiple services verify tokens independently.

- **8-hour access token** — balances security with UX. Refresh tokens
  (30-day, stored in DB) are planned but not implemented yet.

- **Logout is client-side in v1** — JWT is stateless; real server-side
  invalidation requires Redis blacklist (planned for when refresh tokens land).

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
- **Server-side token blacklist** — Redis set of revoked access token JTIs, checked on every request
- **Google OAuth** — redirect flow → callback → JWT
- **Microsoft OAuth** — same pattern
- **Password reset** — email link → reset form → update hash
