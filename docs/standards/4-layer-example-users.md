# 4-Layer Architecture — Real Example: Users

> This document walks through the **Users** feature end-to-end across all
> 4 layers of the hexagonal architecture. Use it as a reference when
> building new features.

---

## Overview

```
Browser                                         Postgres
   │                                                │
   │  HTTP request                                  │
   ▼                                                │
┌──────────────────────────────────────┐            │
│  LAYER 1: API (Entry)                │            │
│  api/v1/users/router.py             │            │
│  api/v1/users/schemas.py            │            │
│                                      │            │
│  Job: Parse HTTP → call service →    │            │
│       format response. THIN.         │            │
└──────────────┬───────────────────────┘            │
               │                                    │
               ▼                                    │
┌──────────────────────────────────────┐            │
│  LAYER 2: SERVICE (Orchestration)    │            │
│  services/user_service.py            │            │
│                                      │            │
│  Job: Business logic. Who can see    │            │
│       what? Validate rules. Hash     │            │
│       passwords. Coordinate repos.   │            │
└──────────────┬───────────────────────┘            │
               │                                    │
               ▼                                    │
┌──────────────────────────────────────┐            │
│  LAYER 3: DOMAIN (Pure Logic)        │            │
│  domain/entities/user.py             │            │
│  domain/exceptions.py                │            │
│                                      │            │
│  Job: Data shape (Pydantic models),  │            │
│       enums, pure business methods.  │            │
│       ZERO external dependencies.    │            │
└──────────────────────────────────────┘            │
               │                                    │
               ▼                                    │
┌──────────────────────────────────────┐            │
│  LAYER 4: ADAPTER (Infrastructure)   │            │
│  adapters/storage/postgres/user/     │            │
│    models.py (SQLAlchemy ORM)        │            │
│    repositories.py (SQL queries)     │            │
│                                      │            │
│  Job: Talk to Postgres. Translate    │            │
│       ORM ↔ domain entity.          │            │
└──────────────────────────────────────┴────────────┘
```

---

## Every file involved

All paths are relative to `backend/app/`.

| Layer | File | What it does |
|-------|------|--------------|
| **L1 API** | `api/v1/users/router.py` | Route handlers — POST/GET/PATCH/DELETE. Thin wrappers around the service. |
| **L1 API** | `api/v1/users/schemas.py` | Request/response Pydantic models (CreateUserRequest, UserResponse, etc.) with Swagger examples. |
| **L1 API** | `api/dependencies/auth.py` | `get_current_user` extracts JWT → `TokenPayload`. `require_role()` checks permissions. |
| **L1 API** | `api/dependencies/database.py` | `get_session` yields an `AsyncSession` per request. |
| **L1 API** | `api/error_handler.py` | Global handler: catches `AppError` → returns JSON with HTTP status code. |
| **L2 Service** | `services/user_service.py` | `UserService` class — create, get, list, update, soft_delete. All business logic lives here. |
| **L3 Domain** | `domain/entities/user.py` | `User` Pydantic model + `Role` enum. Pure methods: `is_super_admin()`, `can_manage_company()`. |
| **L3 Domain** | `domain/exceptions.py` | `UserNotFoundError`, `UserAlreadyExistsError`, `InvalidCredentialsError`, etc. |
| **L4 Adapter** | `adapters/storage/postgres/user/models.py` | `UserORM` — SQLAlchemy table model. Maps to the `users` Postgres table. |
| **L4 Adapter** | `adapters/storage/postgres/user/repositories.py` | `UserRepository` — CRUD methods that return domain `User` entities, not ORM objects. |

---

## Import rules

```
✓ ALLOWED                              ✗ NEVER

router.py → user_service.py            router.py → repositories.py
             (L1 → L2)                              (L1 → L4, skips L2)

user_service.py → user.py              user.py → repositories.py
                   (L2 → L3)                       (L3 → L4)

user_service.py → repositories.py      user.py → user_service.py
                   (L2 → L4)                       (L3 → L2)

repositories.py → user.py              repositories.py → router.py
                   (L4 → L3)                              (L4 → L1)
```

**The rule:** imports flow inward. Domain (L3) is the center — it imports
nothing from the other layers. Everything else can import from domain.

---

## Operation-by-operation walkthrough

### 1. Create User — `POST /api/v1/users`

**Who can call:** super_admin only.

```
Route (router.py)
  │ Parses CreateUserRequest (email, password, role, company_id)
  │ JWT is validated by require_super_admin dependency
  │ Calls service.create_user(caller, email, role, ...)
  │
  ▼
Service (user_service.py)
  │ Checks caller.role == super_admin (permission)
  │ Validates: company_id required for non-super_admin roles
  │ Validates: password or oauth_provider must be provided
  │ Hashes password with argon2 via core/security.py
  │ Calls repo.create(email, role, company_id, password_hash)
  │ Commits the transaction
  │
  ▼
Repository (repositories.py)
  │ Creates UserORM instance
  │ Inserts into Postgres
  │ Catches IntegrityError → raises UserAlreadyExistsError
  │ Translates ORM → domain User entity via _to_domain()
  │ Returns User
  │
  ▼
Route receives User, maps to UserResponse, returns 201
```

### 2. List Users — `GET /api/v1/users?limit=50&offset=0`

**Who can call:** any authenticated user. Results are scoped by role.

```
Route (router.py)
  │ Parses limit/offset query params
  │ JWT is validated by get_current_user dependency
  │ Calls service.list_users(caller, limit, offset)
  │
  ▼
Service (user_service.py)
  │ Checks caller.role:
  │   super_admin → repo.list_all(limit, offset)
  │   others      → repo.list_by_company(caller.company_id, limit, offset)
  │
  ▼
Repository (repositories.py)
  │ SELECT * FROM users WHERE company_id = ? ORDER BY created_at DESC
  │ Translates each ORM row → domain User entity
  │ Returns list[User]
  │
  ▼
Route maps each User → UserResponse, returns 200 with JSON array
```

### 3. Get User — `GET /api/v1/users/{user_id}`

```
Route → service.get_user(user_id)
      → repo.find_by_id(user_id)
      → returns User or raises UserNotFoundError (→ 404)
```

### 4. Update User — `PATCH /api/v1/users/{user_id}`

**Who can call:** admin or above.

```
Route (router.py)
  │ Parses UpdateUserRequest (only provided fields via exclude_unset)
  │ Calls service.update_user(user_id, **fields)
  │
  ▼
Service (user_service.py)
  │ Checks user exists (raises UserNotFoundError if not)
  │ Calls repo.update(user_id, **fields)
  │ Commits the transaction
  │
  ▼
Repository (repositories.py)
  │ UPDATE users SET ... WHERE id = ?
  │ Refreshes the ORM row (picks up server-side updated_at)
  │ Returns updated User entity
```

### 5. Soft-Delete User — `DELETE /api/v1/users/{user_id}`

**Who can call:** admin or above. Does NOT remove the row.

```
Route → service.soft_delete_user(user_id)
      → repo.update(user_id, is_active=False)
      → commits → returns 204 No Content
```

---

## The schemas (API contract)

### CreateUserRequest

```json
{
  "email": "admin@acme.com",
  "password": "SecureP@ss123",
  "role": "admin",
  "company_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- `password` required unless `oauth_provider` is set
- `company_id` required for admin/manager/worker, null for super_admin
- `role` must be one of: `super_admin`, `admin`, `manager`, `worker`

### UpdateUserRequest

```json
{
  "role": "manager",
  "is_active": true
}
```

- Only provided fields are updated (PATCH semantics via `exclude_unset`)
- Missing fields are ignored, not set to null

### UserResponse

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

- Never includes `password_hash` — credentials never cross the API boundary

---

## Role-based access control

| Endpoint | super_admin | admin | manager | worker |
|----------|:-----------:|:-----:|:-------:|:------:|
| `POST /users` (create) | ✓ | ✗ | ✗ | ✗ |
| `GET /users` (list) | all users | company only | company only | company only |
| `GET /users/{id}` (get) | ✓ | ✓ | ✓ | ✓ |
| `PATCH /users/{id}` (update) | ✓ | ✓ | ✗ | ✗ |
| `DELETE /users/{id}` (soft-delete) | ✓ | ✓ | ✗ | ✗ |

Permission checks live in **two places**:
1. **Dependencies** (`require_super_admin`, `require_admin`) — block the request before it reaches the service
2. **Service** (`list_users`) — scopes the data after the request is authorized

---

## Database schema

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id) ON DELETE CASCADE,  -- NULL for super_admin
    email           TEXT NOT NULL,
    password_hash   TEXT,                -- NULL if OAuth-only
    oauth_provider  TEXT,                -- 'google' | 'microsoft' | NULL
    oauth_id        TEXT,
    role            TEXT NOT NULL,        -- CHECK: super_admin/admin/manager/worker
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (email, company_id),          -- same email can exist in different companies
    CHECK (role IN ('super_admin', 'admin', 'manager', 'worker')),
    CHECK (oauth_provider IS NULL OR oauth_provider IN ('google', 'microsoft'))
);

-- Partial unique index for super_admin (company_id IS NULL)
CREATE UNIQUE INDEX ix_users_email_super_admin ON users (email)
    WHERE company_id IS NULL;
```

---

## How to test from Swagger

1. Open http://localhost:8000/docs
2. **POST `/api/v1/auth/login`** → enter email + password → Execute → copy the `access_token`
3. Click **Authorize** (lock icon) → paste the token → Authorize
4. **GET `/api/v1/users`** → Execute → see all users
5. **POST `/api/v1/users`** → use the pre-filled example → Execute → creates a user
6. **PATCH `/api/v1/users/{id}`** → change role → Execute
7. **DELETE `/api/v1/users/{id}`** → Execute → sets is_active=false

---

## Why the domain layer matters — Conversation example

Users is a simple entity — mostly CRUD, thin domain. To understand **why
the domain layer exists**, look at Conversation, where it carries real
business logic:

### Domain (Layer 3) — pure logic, zero infrastructure

```python
# domain/entities/conversation.py — NO imports from FastAPI, SQLAlchemy, MongoDB

class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING_RESPONSE = "WAITING_RESPONSE"
    CLOSED = "CLOSED"

class ClosedReason(StrEnum):
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    MANUAL = "MANUAL"

class Conversation(BaseModel):
    conversation_id: UUID
    company_id: str
    phone: str
    status: ConversationStatus
    last_activity_at: datetime
    reminder_sent_at: datetime | None = None
    session_started_at: datetime
    message_count: int = 0

    def should_send_reminder(self, now: datetime) -> bool:
        """90 min with no activity → send 'are you still there?' reminder."""
        if self.status != ConversationStatus.ACTIVE:
            return False
        return (now - self.last_activity_at).total_seconds() > 5400

    def should_auto_close(self, now: datetime) -> bool:
        """30 min after reminder with no response → auto-close."""
        if self.status != ConversationStatus.WAITING_RESPONSE:
            return False
        if self.reminder_sent_at is None:
            return False
        return (now - self.reminder_sent_at).total_seconds() > 1800

    def is_expired(self, now: datetime) -> bool:
        """2-hour session window passed → start a new conversation."""
        return (now - self.session_started_at).total_seconds() > 7200

    def close(self, reason: ClosedReason) -> None:
        """Transition to CLOSED with the given reason."""
        self.status = ConversationStatus.CLOSED
        self.closed_reason = reason
```

**Notice:** zero imports from FastAPI, SQLAlchemy, MongoDB, WhatsApp, Redis.
Pure Python + Pydantic. The domain doesn't know WHERE conversations are
stored or HOW reminders are sent. It only knows the **rules**.

### Service (Layer 2) — orchestrates domain + adapters

```python
# services/conversation_service.py

class ConversationService:
    def __init__(self, conversation_repo, whatsapp_client):
        self._repo = conversation_repo          # adapter (MongoDB)
        self._whatsapp = whatsapp_client         # adapter (WhatsApp API)

    async def check_expired_sessions(self) -> None:
        """Called by Celery Beat every 5 minutes (session_task).

        The service ORCHESTRATES. The domain DECIDES. The adapter ACTS.
        """
        now = utcnow()

        # ── Step 1: Send reminders to idle conversations ──────
        active = await self._repo.find_by_status("ACTIVE")
        for conv in active:
            if conv.should_send_reminder(now):          # ← DOMAIN decides
                await self._whatsapp.send_text(          # ← ADAPTER acts
                    conv.phone, "Are you still there?"
                )
                conv.status = ConversationStatus.WAITING_RESPONSE
                conv.reminder_sent_at = now
                await self._repo.update(conv)            # ← ADAPTER persists

        # ── Step 2: Auto-close timed-out conversations ────────
        waiting = await self._repo.find_by_status("WAITING_RESPONSE")
        for conv in waiting:
            if conv.should_auto_close(now):              # ← DOMAIN decides
                conv.close(ClosedReason.TIMEOUT)         # ← DOMAIN acts
                await self._repo.update(conv)            # ← ADAPTER persists
```

### What each layer does in this flow

```
DOMAIN:     "SHOULD we send a reminder?"  →  should_send_reminder(now) → True/False
            "SHOULD we auto-close?"       →  should_auto_close(now) → True/False
            "Close it."                   →  close(TIMEOUT) → changes status field

SERVICE:    "Find active conversations"   →  calls repo (adapter)
            "If domain says yes, do it"   →  calls whatsapp (adapter)
            "Save the result"             →  calls repo (adapter)
            "Do it in the right order"    →  orchestration

ADAPTER:    "db.conversations.find(...)"  →  MongoDB query
            "POST to WhatsApp API"        →  HTTP call
            "db.conversations.update(...)" → MongoDB update
```

### Why this matters — testing

Domain logic is testable **without mocks, without a database, without Docker**:

```python
# tests/unit/test_conversation.py — runs in milliseconds, no infra needed

def test_should_send_reminder_after_90_min():
    conv = Conversation(
        status=ConversationStatus.ACTIVE,
        last_activity_at=datetime(2026, 4, 9, 10, 0),
        session_started_at=datetime(2026, 4, 9, 10, 0),
        ...
    )
    now = datetime(2026, 4, 9, 11, 31)  # 91 minutes later
    assert conv.should_send_reminder(now) is True

def test_should_not_remind_if_already_waiting():
    conv = Conversation(status=ConversationStatus.WAITING_RESPONSE, ...)
    assert conv.should_send_reminder(now) is False

def test_auto_close_after_reminder_timeout():
    conv = Conversation(
        status=ConversationStatus.WAITING_RESPONSE,
        reminder_sent_at=datetime(2026, 4, 9, 10, 0),
        ...
    )
    now = datetime(2026, 4, 9, 10, 31)  # 31 minutes after reminder
    assert conv.should_auto_close(now) is True

def test_close_sets_status_and_reason():
    conv = Conversation(status=ConversationStatus.ACTIVE, ...)
    conv.close(ClosedReason.TIMEOUT)
    assert conv.status == ConversationStatus.CLOSED
    assert conv.closed_reason == ClosedReason.TIMEOUT
```

**Zero mocks. Zero database. Pure logic.** If you put this logic in the
service, you'd need to mock the repo and the WhatsApp client just to test
a time comparison. With the domain layer, you test the rules in isolation.

### Without domain (bad) vs with domain (good)

**Without domain** — logic crammed into the service:

```python
# Everything mixed together — hard to test, easy to break
async def check_expired_sessions(self):
    active = await self._repo.find_by_status("ACTIVE")
    for conv in active:
        if conv.status == "ACTIVE":                          # ← logic here
            elapsed = (now - conv.last_activity_at).seconds  # ← logic here
            if elapsed > 5400:                               # ← magic number
                await self._whatsapp.send_text(...)
                conv.status = "WAITING_RESPONSE"             # ← mutation here
```

Problems: testing requires mocking repo + whatsapp. The 5400-second rule
is buried. If a worker and a CLI script both need the same logic, they
copy-paste it.

**With domain** — logic in the entity, orchestration in the service:

```python
# Service is clean
if conv.should_send_reminder(now):    # domain answers yes/no
    await self._whatsapp.send(...)    # adapter does the work
```

The rule is defined **once** in the domain entity. The service, the worker,
the CLI script, and the test all call the same method.

### Domain complexity per entity

| Entity | Domain logic | Domain value |
|--------|-------------|--------------|
| **User** | Low — data shape + Role enum | Decouples API from DB, provides single source for roles |
| **Conversation** | **High** — state machine, 3 time-based rules, 4 close reasons | Core business logic, testable without infra |
| **Resident** | Medium — verification, eligibility, building checks | Gatekeeps who can use the agent |
| **CompanyConfig** | Low — data shape with resolved secrets | Separates raw config from resolved config |

Users is the **simplest** entity. The domain layer doesn't do much for it
today, but having the pattern in place means Conversation (which needs it
badly) follows the same structure. Your team learns one pattern, applies
it everywhere.

---

## The golden rule

> **Routes are thin. Services are smart. Domain is pure. Adapters are isolated.**

When you're not sure where code belongs, ask:

| Question | Layer |
|----------|-------|
| "Does this parse HTTP or format a response?" | **L1 — Route** |
| "Does this coordinate multiple things or check permissions?" | **L2 — Service** |
| "Is this a data shape or a pure business rule?" | **L3 — Domain** |
| "Does this talk to a database, API, or external system?" | **L4 — Adapter** |
