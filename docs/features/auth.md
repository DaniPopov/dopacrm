# Feature: Auth

## Summary

Email + password authentication for the dashboard. Returns a JWT access
token that authenticates all subsequent API requests. super_admin users
can log in without a company scope. OAuth (Google/Microsoft) is planned
for Phase 2 — the database schema supports it but no routes exist yet.

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | `/api/v1/auth/login` | None | 10/min/IP | Email + password → JWT access token |
| GET | `/api/v1/auth/me` | Bearer | — | Current user profile from token |

## Domain (Layer 3)

### Entities

- **`domain/entities/user.py`** — `User` + `Role` enum (shared with Users feature)

### Exceptions

- `InvalidCredentialsError` → 401 (wrong email or password)

## Service (Layer 2)

Auth orchestration currently lives inline in the route handler (no
separate auth_service.py — was deleted because it was just a re-export
wrapper). When refresh tokens and logout are added, create
`services/auth_service.py` with:

- `login(email, password, company_id)` → validate credentials, return token pair
- `refresh(refresh_token)` → validate, rotate, return new access token
- `logout(refresh_token)` → revoke token in DB

## Adapter (Layer 4)

### Repository methods used

- `UserRepository.find_with_credentials(email, company_id)` — returns
  `(User, password_hash)` tuple. The hash leaves the repo here but the
  route verifies and discards it immediately.

### Security utilities

File: `core/security.py`

- `hash_password(plain) → str` — argon2id hash
- `verify_password(plain, hashed) → bool` — constant-time comparison
- `create_access_token(user_id, role, company_id, secret_key) → str` — HS256 JWT, 8h expiry
- `decode_access_token(token, secret_key) → TokenPayload` — decodes + validates
- `TokenPayload` — Pydantic model: sub (user ID), role, company_id, type

### JWT details

| Field | Value |
|-------|-------|
| Algorithm | HS256 |
| Signing key | `APP_SECRET_KEY` (min 32 chars, SecretStr) |
| Access token expiry | 8 hours |
| Payload fields | sub (user UUID), role, company_id, type ("access"), iat, exp |

## API (Layer 1)

### Routes

File: `api/v1/auth/router.py`

- **POST `/login`** — accepts JSON `{email, password}`. Looks up user by
  email (tries super_admin first, then any user). Verifies password with
  argon2. Returns `{access_token, token_type, expires_in}`.
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
  - Shortcuts: `require_super_admin`, `require_admin`, `require_manager`

### Rate limiting

- `/login` → `login_rate_limit` (10 requests/min per IP) — brute-force protection
- `/me` → no rate limit (already requires a valid token)

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_security.py` | argon2 hash format, uniqueness, verify match/mismatch, needs_rehash |
| E2E | `tests/e2e/test_auth.py` | login success, wrong password (401), nonexistent email (401), /me with/without token, SQL injection in email/password/UNION SELECT |

### Test count

- Unit: 5 tests (password hashing + verification)
- E2E: 8 tests (login flow + SQL injection security)
- **Total: 13 auth-related tests, all passing**

### Security tests (across auth + users E2E)

| Test | What it proves |
|------|---------------|
| SQL injection in email | Rejected (401/422), no 500 |
| SQL injection in password | 401, no auth bypass |
| UNION SELECT injection | Rejected, no data leak |
| XSS in email | 422, Pydantic rejects |
| Tampered JWT (wrong signature) | 401 |
| Forged role escalation (wrong key) | 401 |
| Worker creating user (super_admin only) | 403 |
| Manager deleting user (admin+ only) | 403 |
| Admin with null company_id listing users | 403, not all users |

## Decisions

- **JWT over session cookies** — the dashboard is a React SPA (Phase 2).
  SPAs work better with Bearer tokens than cookies (no CSRF issues, works
  across origins, mobile-friendly). Cookies can be added later if needed.

- **HS256 over RS256** — single service, no need for asymmetric keys.
  HS256 is simpler (one shared secret). Switch to RS256 if/when multiple
  services need to verify tokens independently.

- **8-hour access token** — balances security (shorter = safer) with UX
  (users don't want to re-login every hour). Refresh tokens (30-day,
  stored in DB) are planned but not implemented yet.

- **HTTPBearer over OAuth2PasswordBearer** — simpler Swagger UI. Shows
  one "Bearer token" input instead of the confusing OAuth2 form with
  grant_type/scope/client_id fields. OAuth2 is for Phase 2.

- **No separate auth_service.py** — login logic is simple enough to live
  in the route handler for now. Create the service when refresh/logout
  flows arrive (they need to coordinate user_repo + token_repo + security).

- **Rate limiting on /login only** — brute-force protection at the entry
  point. Other endpoints require a valid JWT, which is its own protection.

## Swagger

1. Open http://localhost:8000/docs
2. **POST `/api/v1/auth/login`** → enter email + password → Execute
3. Copy the `access_token` from the response
4. Click **Authorize** (lock icon, top-right) → paste token → Authorize
5. All protected endpoints now work with "Try it out"

## Planned (Phase 2)

- **Refresh tokens** — POST `/api/v1/auth/refresh` with refresh token → new access token
- **Logout** — POST `/api/v1/auth/logout` → revoke refresh token in DB
- **Google OAuth** — redirect flow → callback → JWT
- **Microsoft OAuth** — same pattern
- **Password reset** — email link → reset form → update hash
