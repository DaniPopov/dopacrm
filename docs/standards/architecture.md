# Architecture Standards

> Rules for the 4-layer hexagonal architecture.
> Every developer (including AI) must follow these.

## The 4 Layers

```
api/        → LAYER 1: ENTRY (Ports)
services/   → LAYER 2: ORCHESTRATION (Use Cases)
domain/     → LAYER 3: THE BRAIN (Pure Logic & State)
adapters/   → LAYER 4: INFRASTRUCTURE (Adapters)
```

## The One Rule

**Imports flow inward. Domain is the center.**

```
api → services → domain ← adapters
```

| Layer | Can import from | Cannot import from |
|-------|----------------|-------------------|
| `api/` | `services`, `domain` | `adapters` |
| `services/` | `domain`, `adapters` | `api` |
| `domain/` | nothing | `api`, `services`, `adapters` |
| `adapters/` | `domain` | `api`, `services` |

**The critical implication:** `domain/` has zero dependencies on infrastructure. It doesn't know SQLAlchemy exists. It doesn't know what S3 is. It only knows pure Python and Pydantic.

---

## Layer 1: API (`app/api/`)

**What it does:** Receives HTTP requests, validates input, calls the right service, returns HTTP responses.

**What goes here:**

- FastAPI route handlers
- Request/response Pydantic schemas (specific to the HTTP contract)
- JWT extraction and tenant scoping (via `dependencies.py`)
- Rate limiting middleware
- HTTP exception mapping (domain errors → HTTP status codes)

**What does NOT go here:**

- Business logic (even "simple" logic like "if resident is not verified, reject")
- Direct database calls
- Direct calls to external APIs

**Rules:**

- Route handlers are thin — validate input, call service, return response
- One router file per resource group (`routes/whatsapp.py`, `routes/auth.py`, `routes/companies.py`)
- All routes are versioned: `/api/v1/...`
- Request schemas are separate from domain entities (API may expose a subset of fields)

```python
# app/api/routes/companies.py

@router.get("/{company_id}/config")
async def get_company_config(
    company_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> ConfigResponse:
    """Route handler — thin. Delegates to service."""
    config = await config_manager.get_config(tenant.company_id)
    return ConfigResponse.from_domain(config)
```

---

## Layer 2: Services (`app/services/`)

**What it does:** Orchestrates operations. Coordinates between domain logic and adapters to fulfill a use case.

**What goes here:**

- Use case implementations ("handle incoming WhatsApp message", "verify resident identity")
- Coordination logic — calling adapters in the right order, passing data between them
- Transaction boundaries — if something fails midway, handle rollback/compensation

**What does NOT go here:**

- HTTP concepts (request objects, status codes, headers)
- Raw database queries
- Direct API client calls
- Pure business rules (those go in domain)

**Rules:**

- One service file per bounded context (`config_manager.py`, `agent_service.py`, `auth_service.py`)
- Services receive and return domain entities — not raw dicts, not HTTP schemas
- Services call adapters through their public interface — never reach into adapter internals
- A service can call another service only when necessary (prefer flat orchestration over deep nesting)

```python
# app/services/agent_service.py

class AgentService:
    def __init__(self, config_manager: ConfigManager, erp: ERPAdapter, messaging: WhatsAppAdapter):
        self._config = config_manager
        self._erp = erp
        self._messaging = messaging

    async def handle_message(self, phone: str, text: str, company_id: str) -> None:
        """Orchestrate: load config → load conversation → run agent → send response."""
        config = await self._config.get_config(company_id)
        conversation = await self._conversations.load_or_create(phone, company_id)
        response = await self._run_agent(conversation, text, config)
        await self._messaging.send_text(phone, response.text)
        await self._conversations.update(conversation)
```

---

## Layer 3: Domain (`app/domain/`)

**What it does:** Contains pure business logic, entity definitions, and state machines. The brain of the application.

**What goes here:**

- Pydantic entity models (`entities/resident.py`, `entities/conversation.py`, `entities/config.py`)
- Pure business logic functions (validation, state transitions, calculations)
- LangGraph agent definitions — nodes, edges, state (`agent/`)
- Custom domain exceptions (`exceptions.py`)
- Enums and constants

**What does NOT go here:**

- Anything with `import` from `fastapi`, `motor`, `redis`, `boto3`, `httpx`
- Any I/O — no database calls, no HTTP calls, no file reads
- Any framework-specific code

**Rules:**

- **Zero external dependencies** — only stdlib + Pydantic
- All functions are pure when possible — same input → same output, no side effects
- Entity models define the shape of data and validation rules
- State machines are explicit (conversation status transitions)

```python
# app/domain/entities/conversation.py

class ConversationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_RESPONSE = "WAITING_RESPONSE"
    CLOSED = "CLOSED"

class Conversation(BaseModel):
    conversation_id: str
    company_id: str
    phone: str
    status: ConversationStatus = ConversationStatus.ACTIVE
    last_activity_at: datetime

    def should_send_reminder(self, now: datetime) -> bool:
        """Pure logic — no I/O."""
        if self.status != ConversationStatus.ACTIVE:
            return False
        return (now - self.last_activity_at).total_seconds() > 5400  # 90 min

    def close(self, reason: ClosedReason) -> None:
        self.status = ConversationStatus.CLOSED
        self.closed_reason = reason
```

### LangGraph in Domain

The LangGraph agent graph definition lives in `domain/agent/` because the graph structure (which nodes exist, how they connect, what state they manage) is core business logic. But the actual tools that call external APIs (Priority, WhatsApp) are adapters injected at runtime.

```
domain/agent/
├── graph.py        # Graph definition — nodes, edges, conditional routing
├── state.py        # TypedDict for LangGraph state
├── nodes.py        # Node functions (pure logic + calls to injected tools)
└── prompts.py      # System prompt templates
```

---

## Layer 4: Adapters (`app/adapters/`)

**What it does:** Implements all external I/O. Talks to databases, APIs, cloud services. Translates between external formats and domain entities.

**What goes here:**

- Database clients and queries (Postgres via SQLAlchemy, Redis)
- Cloud service clients (S3, Secrets Manager)
- Data mappers — convert ORM rows / API responses to domain entities

**What does NOT go here:**

- Business logic (even "simple" stuff like default values or fallbacks — that's domain)
- HTTP routing or request handling
- Orchestration between multiple adapters (that's a service's job)

**Rules:**

- Each adapter is self-contained — owns its client, connection, and data mapping
- Adapters accept and return domain entities (not raw dicts to the outside)
- Adapters handle their own retries and connection management
- Adapters translate infrastructure errors into domain exceptions

```python
# app/adapters/storage/postgres/payment/repositories.py

class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, payment_id: UUID) -> Payment | None:
        """Adapter — talks to Postgres, returns domain entity."""
        result = await self._session.execute(
            select(PaymentORM).where(PaymentORM.id == payment_id)
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None
```

---

## How to Add a New Feature

Example: "Add support for announcements"

**Step 1 — Domain first.** Define the entity and any pure logic:

```
domain/entities/announcement.py  → Pydantic model
```

**Step 2 — Adapter.** Add persistence:

```
adapters/storage/postgres/announcement/repositories.py  → CRUD operations
```

**Step 3 — Service.** Orchestrate the use case:

```
services/announcement_service.py  → load, create, update announcements
```

**Step 4 — API.** Expose via HTTP:

```
api/routes/announcements.py  → GET/POST/PUT routes
```

Always build from the inside out: **domain → adapter → service → api**.

---

## Dependency Injection

Services and adapters are wired together at startup, not inside each other.

```python
# app/api/v1/payments/router.py — services + adapters wired per request

def _get_service(session: AsyncSession = Depends(get_session)) -> PaymentService:
    """FastAPI builds a fresh PaymentService per request, injecting an
    AsyncSession from the connection pool. The service constructs its
    own repositories from that session — no manual DI container."""
    return PaymentService(session)
```

This makes testing trivial — swap real adapters with fakes.

---

## When to Create a New Service vs Extend

**New service** when:

- The use case has a clearly different bounded context (auth ≠ conversations)
- It coordinates a different set of adapters
- You can name it without using "and" ("AuthService", not "AuthAndProfileService")

**Extend existing** when:

- The new function naturally belongs to the same bounded context
- It uses the same adapters the service already depends on
- Moving it out would create a service with only 1-2 methods

---

## Real Example: Users (4-Layer Walkthrough)

This section shows how a single feature (Users) flows through all 4 layers.
Use it as a reference when building new features.

### Request: `GET /api/v1/users` (list users, company-scoped)

```
Browser → FastAPI → Route → Service → Repository → Postgres
                     (L1)    (L2)       (L4)
```

### Layer 1 — API (`api/v1/users/router.py`)

The route is **thin**. It does three things: parse input, call service, format output.

```python
@router.get("", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    caller: TokenPayload = Depends(get_current_user),  # JWT → identity
    service: UserService = Depends(_get_service),       # DI
) -> list[UserResponse]:
    users = await service.list_users(caller, limit=limit, offset=offset)
    return [_to_response(u) for u in users]
```

**What it does NOT do:** permission checks, database queries, hashing, business rules.

### Layer 2 — Service (`services/user_service.py`)

The service **owns the business logic**. This is where "who can see what" lives:

```python
async def list_users(self, caller: TokenPayload, *, limit, offset) -> list[User]:
    if caller.role == "super_admin":
        return await self._repo.list_all(limit=limit, offset=offset)
    return await self._repo.list_by_company(
        UUID(caller.company_id), limit=limit, offset=offset
    )
```

**What it does NOT do:** parse HTTP, return JSON, talk to the database directly.

### Layer 3 — Domain (`domain/entities/user.py`)

The domain entity is a **pure Pydantic model**. No imports from FastAPI,
SQLAlchemy, or any adapter. Just data shape + business logic methods:

```python
class User(BaseModel):
    id: UUID
    company_id: UUID | None
    email: str
    role: Role
    is_active: bool

    def can_manage_company(self, company_id: UUID) -> bool:
        if self.is_super_admin():
            return True
        return self.company_id == company_id
```

**What it does NOT do:** HTTP, SQL, caching, external API calls.

### Layer 4 — Adapter (`adapters/storage/postgres/user/repositories.py`)

The repository **talks to Postgres** and translates between the SQLAlchemy
ORM and the Pydantic domain entity:

```python
async def list_by_company(self, company_id: UUID, *, limit, offset) -> list[User]:
    result = await self._session.execute(
        select(UserORM)
        .where(UserORM.company_id == company_id)
        .order_by(UserORM.created_at.desc())
        .limit(limit).offset(offset)
    )
    return [_to_domain(orm) for orm in result.scalars()]
```

**What it does NOT do:** permission checks, HTTP, business rules.

### Files involved (all in `backend/app/`)

| Layer | File | Responsibility |
|-------|------|----------------|
| **L1 API** | `api/v1/users/router.py` | HTTP in/out, thin |
| **L1 API** | `api/v1/users/schemas.py` | Request/response Pydantic models |
| **L1 API** | `api/dependencies/auth.py` | JWT → TokenPayload |
| **L1 API** | `api/dependencies/database.py` | AsyncSession per request |
| **L2 Service** | `services/user_service.py` | Business logic, orchestration |
| **L3 Domain** | `domain/entities/user.py` | User + Role, pure logic |
| **L3 Domain** | `domain/exceptions.py` | UserNotFoundError, etc. |
| **L4 Adapter** | `adapters/storage/postgres/user/models.py` | SQLAlchemy ORM |
| **L4 Adapter** | `adapters/storage/postgres/user/repositories.py` | SQL queries |

### Import direction (the rule)

```
router.py  imports  user_service.py   ✓  (L1 → L2)
user_service.py  imports  user.py     ✓  (L2 → L3)
user_service.py  imports  repositories.py  ✓  (L2 → L4)
repositories.py  imports  user.py     ✓  (L4 → L3)
user.py  imports  nothing from app    ✓  (L3 → nothing)

router.py  imports  repositories.py   ✗  NEVER (L1 → L4 skips L2)
user.py  imports  repositories.py     ✗  NEVER (L3 → L4)
```

### The golden rule

> **Routes are thin. Services are smart. Domain is pure. Adapters are isolated.**

When you're not sure where code belongs, ask: "Does this need HTTP?" (L1)
"Does this coordinate multiple things?" (L2) "Is this a business rule?" (L3)
"Does this talk to an external system?" (L4).

---

## Multi-Tenancy in Each Layer

Every layer participates in tenant isolation:

| Layer | How |
|-------|-----|
| **API** | `dependencies.py` extracts `company_id` from JWT → passes as `TenantContext` |
| **Services** | Every method receives `company_id` as parameter — never optional |
| **Domain** | Every entity has `company_id` field |
| **Adapters** | Every query filters by `company_id` — enforced in repository base class |
