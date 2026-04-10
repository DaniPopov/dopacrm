# Feature: Users

## Summary

Dashboard user management — CRUD for the platform's admin/manager/worker
users. super_admin creates users and assigns them to companies. Each user
belongs to exactly one company (except super_admin who has no company).
Supports email+password and OAuth (Google/Microsoft) authentication.

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | `/api/v1/auth/login` | None | 10/min/IP | Email + password → JWT access token |
| GET | `/api/v1/auth/me` | Bearer | 60/min/user | Current user profile from token |
| POST | `/api/v1/users` | super_admin | 60/min/user | Create a new user |
| GET | `/api/v1/users` | Bearer | 60/min/user | List users (company-scoped by role) |
| GET | `/api/v1/users/{id}` | Bearer | 60/min/user | Get user by ID |
| PATCH | `/api/v1/users/{id}` | admin+ | 60/min/user | Partial update |
| DELETE | `/api/v1/users/{id}` | admin+ | 60/min/user | Soft-delete (is_active=false) |

## Domain (Layer 3)

### Entities

- **`domain/entities/user.py`** — `User` Pydantic model + `Role` StrEnum
  - Fields: id, company_id (nullable), email, role, is_active, oauth_provider, created_at, updated_at
  - `Role`: super_admin / admin / manager / worker
  - Does NOT carry password_hash — credentials are a separate concern

- **`domain/entities/company.py`** — `Company` Pydantic model
  - Fields: id, slug, name, phone, is_active, created_at, updated_at

- **`domain/entities/refresh_token.py`** — `RefreshToken` Pydantic model
  - Fields: id, user_id, expires_at, is_revoked, created_at
  - Does NOT carry token_hash — same principle as password

### Pure logic methods

- `User.is_super_admin()` — True if role is super_admin
- `User.can_manage_company(company_id)` — True if super_admin OR same company + admin/manager role

### Exceptions

- `UserNotFoundError` → 404
- `UserAlreadyExistsError` → 409
- `InvalidCredentialsError` → 401
- `InsufficientPermissionsError` → 403
- `CompanyNotFoundError` → 404

## Service (Layer 2)

File: `services/user_service.py` — `UserService` class

Methods:
- **`create_user(caller, email, role, company_id, password, ...)`** — validates permissions (super_admin only), validates company_id required for non-super_admin, hashes password via `core/security.py`, calls repo, commits.
- **`get_user(user_id)`** — find by ID, raises `UserNotFoundError` if missing.
- **`list_users(caller, limit, offset)`** — company-scoped: super_admin sees all, others see only their company.
- **`update_user(user_id, **fields)`** — partial update, checks existence first.
- **`soft_delete_user(user_id)`** — sets is_active=False, does not remove the row.

### Business rules

- Only super_admin can create users
- Non-super_admin roles require a company_id
- `list_users` returns only the caller's company unless super_admin
- Password is hashed with argon2 before storage (via `core/security.hash_password`)
- Password hash never leaves the repository layer (not on the domain entity)

## Adapter (Layer 4)

### Database model

File: `adapters/storage/postgres/user/models.py` — `UserORM`

Table: `users`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, server-default gen_random_uuid() |
| company_id | UUID | FK → companies, nullable (NULL for super_admin) |
| email | TEXT | NOT NULL |
| password_hash | TEXT | nullable (NULL for OAuth-only) |
| oauth_provider | TEXT | CHECK: google / microsoft / NULL |
| oauth_id | TEXT | nullable |
| role | TEXT | CHECK: super_admin / admin / manager / worker |
| is_active | BOOLEAN | NOT NULL, default true |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
| updated_at | TIMESTAMPTZ | NOT NULL, default now(), onupdate |

Constraints:
- `UNIQUE (email, company_id)` — same email in different companies OK
- Partial unique index on email WHERE company_id IS NULL — prevents duplicate super_admins
- CHECK on role and oauth_provider values

### Repository methods

File: `adapters/storage/postgres/user/repositories.py` — `UserRepository`

- `create(email, role, company_id, password_hash, ...)` — INSERT, catches IntegrityError → UserAlreadyExistsError
- `find_by_id(user_id)` — SELECT by PK
- `find_by_email(email, company_id)` — SELECT with IS NULL handling for super_admin
- `find_with_credentials(email, company_id)` — returns (User, password_hash) tuple for login
- `list_all(limit, offset)` — paginated, ordered by created_at DESC
- `list_by_company(company_id, limit, offset)` — filtered + paginated
- `update(user_id, **fields)` — partial UPDATE, raises UserNotFoundError

All methods return domain `User` entities, never ORM objects. Translation
happens via the `_to_domain()` helper.

### Migrations

- `0001_create_users_companies_tokens.py` — creates `companies`, `users`, `refresh_tokens` tables with all constraints and indexes.

## API (Layer 1)

### Routes

File: `api/v1/users/router.py`

- `POST ""` → calls `service.create_user()`, returns 201 + UserResponse
- `GET ""` → calls `service.list_users()`, returns list[UserResponse] with limit/offset
- `GET "/{user_id}"` → calls `service.get_user()`, returns UserResponse
- `PATCH "/{user_id}"` → calls `service.update_user()` with exclude_unset fields
- `DELETE "/{user_id}"` → calls `service.soft_delete_user()`, returns 204

File: `api/v1/auth/router.py`

- `POST "/login"` → validates credentials, returns TokenResponse (JWT)
- `GET "/me"` → returns UserResponse for the authenticated token

### Schemas

File: `api/v1/users/schemas.py`

**CreateUserRequest:**
```json
{
  "email": "admin@acme.com",
  "password": "SecureP@ss123",
  "role": "admin",
  "company_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**UpdateUserRequest:**
```json
{
  "role": "manager",
  "is_active": true
}
```

**UserResponse:**
```json
{
  "id": "bb22240d-f00d-47fc-ac60-aa5b08f550aa",
  "email": "admin@acme.com",
  "role": "admin",
  "company_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": true,
  "oauth_provider": null,
  "created_at": "2026-04-09T12:00:00+03:00",
  "updated_at": "2026-04-09T12:00:00+03:00"
}
```

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

### Dependencies used

- `get_current_user` — decodes JWT from Authorization: Bearer header
- `require_super_admin` — blocks non-super_admin callers (403)
- `require_admin` — blocks manager/worker callers (403)
- `api_rate_limit` — 60 requests/min per user (applied at router level)
- `login_rate_limit` — 10 requests/min per IP (applied on /login)
- `get_session` — yields AsyncSession per request

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | `tests/unit/test_user_entity.py` | is_super_admin, can_manage_company for all 4 roles, cross-company access denied |
| Unit | `tests/unit/test_security.py` | argon2 hash format, uniqueness, verify, needs_rehash |
| Unit | `tests/test_health.py` | /health returns 200 |
| Integration | `tests/integration/test_user_repo.py` | create, find_by_id, find_by_email, find_with_credentials, list_all, list_by_company, update, soft_delete, duplicate email — all against real Postgres |
| E2E | `tests/e2e/` | (pending — add when more endpoints exist) |

### Test count

- Unit: 13 tests (user entity logic + security/hashing)
- Integration: 12 tests (repo CRUD against real Postgres)
- E2E: 14 tests (CRUD, auth required, role escalation, JWT tampering, SQL injection, XSS)
- **Total: 39 user-related tests, all passing**

## Decisions

- **Soft-delete vs hard-delete** — chose soft-delete (is_active=False)
  because user data will be referenced by conversations and audit trails.
  Hard-deleting a user would orphan their conversation history.

- **Role as CHECK constraint vs Postgres ENUM** — chose CHECK constraint
  because Postgres ENUMs are hard to migrate (can't easily add values in
  older versions). CHECK is a simple string comparison, more portable.

- **Password hash NOT on domain entity** — the User Pydantic model never
  carries password_hash. Credentials are passed explicitly to repo.create()
  and returned only by repo.find_with_credentials() for the login flow.
  This prevents accidental serialization of password hashes in API
  responses or logs.

- **company_id nullable** — super_admin has company_id=NULL because they
  operate at the platform level, not scoped to any company. A partial
  unique index on (email) WHERE company_id IS NULL prevents duplicate
  super_admin emails without breaking the (email, company_id) constraint
  for company-scoped users.

- **argon2 over bcrypt** — OWASP recommendation since 2021. Memory-hard,
  harder to crack on GPUs. argon2-cffi defaults are safe for 2026 hardware.

- **One Dockerfile for backend + worker** — same image, different command.
  95% overlap in deps and code. Separate Dockerfiles would double build
  time with ~3 MB savings.

## Swagger

How to test from http://localhost:8000/docs:

1. **POST `/api/v1/auth/login`** — enter email + password → Execute → copy `access_token`
2. Click **Authorize** (lock icon) → paste token → Authorize
3. **GET `/api/v1/auth/me`** → see your profile
4. **GET `/api/v1/users`** → see all users (or just your company's)
5. **POST `/api/v1/users`** → create a user with the pre-filled example
6. **PATCH `/api/v1/users/{id}`** → change role or is_active
7. **DELETE `/api/v1/users/{id}`** → soft-delete (sets is_active=false)
