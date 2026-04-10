# Python Standards

> These conventions apply to all Python code in the `app/` directory.

## Python Version

- **3.13+** — use modern syntax (type unions with `|`, `match` statements where appropriate)

## Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Files / modules | `snake_case` | `config_manager.py` |
| Functions / methods | `snake_case` | `get_resolved_config()` |
| Classes | `PascalCase` | `ResidentProfile` |
| Constants | `UPPER_SNAKE` | `MAX_RETRY_COUNT` |
| Pydantic models | `PascalCase` | `CompanyConfig` |
| Type aliases | `PascalCase` | `CompanyId = str` |
| Private (internal) | `_leading_underscore` | `_parse_webhook_body()` |
| Environment vars | `UPPER_SNAKE` | `MONGODB_URI` |

**Booleans** — prefix with `is_`, `has_`, `can_`, `should_`:

```python
is_active: bool
has_takeover: bool
can_send_media: bool
```

## Type Hints

Required on all function signatures — parameters and return types.

```python
# Yes
async def get_config(company_id: str) -> ResolvedConfig:
    ...

# Yes — use | for unions
def find_resident(phone: str) -> Resident | None:
    ...

# No — untyped
def get_config(company_id):
    ...
```

**Collections** — use built-in generics:

```python
# Yes
def get_contacts(company_id: str) -> list[Contact]:
    ...

config: dict[str, Any]
ids: set[str]

# No — don't import from typing for these
from typing import List, Dict  # unnecessary in 3.12+
```

**Internal variables** — type hints optional, use when not obvious:

```python
# Obvious — no hint needed
name = resident.first_name
count = len(messages)

# Not obvious — add hint
config: ResolvedConfig = await _resolve_refs(raw_config)
```

## Imports

Order (enforced by `isort`):

```python
# 1. Standard library
import uuid
from datetime import datetime

# 2. Third-party
from fastapi import APIRouter, Depends
from pydantic import BaseModel

# 3. Local — absolute imports from app root
from app.domain.entities.resident import Resident
from app.services.config_manager import ConfigManager
```

**Rules:**

- Always use absolute imports from `app.` — never relative (`from ..services`)
- One import per line when importing multiple names (if >3 names, use multi-line)
- Never use `import *`

## Functions

### Size & Responsibility

- One function, one job. If you're writing "and" in the description, split it.
- Target: under 30 lines. Not a hard rule — but if a function exceeds 50 lines, it almost certainly needs splitting.

### Async

- All I/O functions must be `async` — database calls, HTTP calls, Redis, S3
- Pure logic functions stay synchronous
- Never call `asyncio.run()` inside the app — let FastAPI/Celery manage the event loop

```python
# I/O — async
async def fetch_resident(phone: str, company_id: str) -> Resident | None:
    return await db.residents.find_one({"phone": phone, "company_id": company_id})

# Pure logic — sync
def is_session_expired(conversation: Conversation) -> bool:
    return datetime.utcnow() > conversation.session_expires_at
```

### Docstrings

**When required:**

- All public functions in `services/` layer (these are the main entry points)
- All Pydantic models in `domain/entities/`
- Complex domain logic in `domain/`

**When NOT needed:**

- Private functions with clear names (`_hash_token`, `_format_phone`)
- Simple CRUD operations in adapters (`insert_resident`, `find_by_id`)
- Route handlers (the route decorator + schema is self-documenting)

**Format — Google style, kept minimal:**

```python
async def resolve_config(company_id: str) -> ResolvedConfig:
    """Load company config with all secrets resolved.

    Checks Redis cache first, falls back to MongoDB + Secrets Manager.
    Caches the resolved result for 5 minutes.

    Args:
        company_id: UUID of the company from Neon.

    Returns:
        Fully resolved config with real secret values (no _ref pointers).

    Raises:
        CompanyNotFoundError: If no config exists for this company_id.
    """
```

**Rules:**

- First line = what it does (imperative mood: "Load", "Send", "Verify" — not "Loads", "Sends")
- `Args` — only if parameters aren't self-explanatory from name + type hint
- `Returns` — only if the return value needs explanation beyond the type hint
- `Raises` — only for exceptions the caller should handle
- Skip sections that add no information. A 1-line docstring is fine:

```python
async def send_text(phone: str, message: str) -> None:
    """Send a WhatsApp text message to a resident."""
```

## Error Handling

### Custom Exceptions

Define in `app/domain/exceptions.py`. All inherit from a base:

```python
class AppError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code

class CompanyNotFoundError(AppError):
    def __init__(self, company_id: str):
        super().__init__(f"Company not found: {company_id}", "COMPANY_NOT_FOUND")

class ResidentNotVerifiedError(AppError):
    def __init__(self, phone: str):
        super().__init__(f"Resident not verified: {phone}", "RESIDENT_NOT_VERIFIED")
```

### Rules

- **Domain layer** raises domain exceptions — never HTTP exceptions
- **API layer** catches domain exceptions and maps to HTTP responses
- **Adapters** catch infrastructure errors (DB timeouts, API failures) and either retry or raise a domain exception
- Never use bare `except:` — always catch specific exceptions
- Let unexpected exceptions bubble up — Sentry will catch them

```python
# In service layer — raise domain error
async def get_config(company_id: str) -> ResolvedConfig:
    config = await mongodb.find_config(company_id)
    if not config:
        raise CompanyNotFoundError(company_id)
    return await _resolve_refs(config)

# In API layer — catch and map
@router.get("/companies/{company_id}/config")
async def get_company_config(company_id: str):
    try:
        return await config_manager.get_config(company_id)
    except CompanyNotFoundError:
        raise HTTPException(status_code=404, detail="Company not found")
```

## Pydantic Models

- All data structures that cross layer boundaries = Pydantic models
- Define in `app/domain/entities/`
- Use `model_config` for MongoDB/JSON compatibility:

```python
from pydantic import BaseModel, Field
from datetime import datetime

class Resident(BaseModel):
    resident_id: str = Field(alias="_id")
    company_id: str
    phone: str
    first_name: str
    last_name: str
    verified: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}
```

## Package Manager

- **uv** — fast Rust-based package manager (Astral, same team as ruff)
- All deps declared in root `pyproject.toml`
- Dev deps in `[dependency-groups] dev` (PEP 735)
- Build backend: hatchling (`packages = ["backend/app"]` so the on-disk path
  `backend/app/` is importable as `app`)
- Common commands:
  - `uv sync` — install all deps from `pyproject.toml`
  - `uv run pytest` — run tests in the project venv
  - `uv run ruff check .` — lint
  - `uv add <package>` — add a new dep
  - `uv lock` — refresh `uv.lock`

## Lazy Imports

Heavy third-party libraries (`boto3`, `motor`, `sqlalchemy`, `langchain`,
`langgraph`, `sentry_sdk`) should be **lazy-imported** — pulled in only when
the code path actually runs, not at module load. Eager imports of these add
seconds to app boot, megabytes to memory, and slow down test collection for
unrelated tests.

### Why

- **Faster app boot** — uvicorn doesn't pull `boto3` (~2-3s, ~50 MB) unless
  something actually touches S3 or Secrets Manager.
- **Faster test runs** — `pytest` collecting `test_resident.py` shouldn't
  trigger a `langchain` import.
- **Smaller blast radius** — a CVE in `boto3` only affects S3-touching paths.
- **Optional features** — Sentry, Langfuse, etc. only initialize if their
  env vars are set.

### The pattern

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import boto3  # type-checker only — zero runtime cost


class S3Client:
    def __init__(self) -> None:
        import boto3  # actual import deferred to first instantiation

        self._client = boto3.client("s3")
```

The `TYPE_CHECKING` block lets you keep type hints (`-> "boto3.client"`) without
paying the runtime cost. The function-level `import` defers the real load until
the class is actually used.

### Where to apply it

| File | Heavy import to defer |
|------|----------------------|
| `app/adapters/cloud/s3_client.py` | `boto3` |
| `app/adapters/cloud/secrets_client.py` | `boto3` |
| `app/adapters/storage/mongodb/database.py` | `motor` / `pymongo` |
| `app/adapters/storage/postgres/database.py` | `sqlalchemy`, `sqlalchemy.ext.asyncio` |
| `app/domain/agent/nodes.py` | `langchain_anthropic`, `langgraph` |
| `app/main.py` lifespan | `sentry_sdk` (only if `SENTRY_DSN` is set) |

### Where NOT to apply it

- **`config.py`** — `Settings` is needed at startup; lazy makes no sense.
- **`domain/entities/`** — Pydantic models evaluate type hints at runtime via
  `get_type_hints()`. Imports they use must stay eager. Ruff is configured
  to recognize Pydantic base classes and skip TC warnings on them.
- **FastAPI route handlers** — registered at app boot, can't defer.
- **`backend/tests/`** — pytest loads everything anyway; lazy imports add
  noise with no benefit. Per-file TC ignores are configured for tests.

### Enforcement

Ruff has the `TC` (flake8-type-checking) ruleset enabled in `pyproject.toml`.
It auto-detects imports used **only** for type annotations and tells you to
move them into a `TYPE_CHECKING` block. Run `ruff check --fix .` to apply.

`TC` only catches *type-checking-only* imports. **Runtime** lazy imports
(like `import boto3` inside `__init__`) are still manual — apply them when
you write the adapter.

## Formatting & Linting

- **Formatter:** `ruff format` (Black-compatible)
- **Linter:** `ruff check` — the `I` rule handles import sorting (replaces `isort`)
- **Line length:** 100 characters
- **Quotes:** double quotes (`"`)
- Config lives in root `pyproject.toml`
- Pre-commit hook auto-fixes on every commit

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]
```
