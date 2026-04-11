# Skill: Build a new backend feature

> Step-by-step recipe for adding a new feature to the FastAPI backend. Follow in order — the 4-layer architecture means each step builds on the previous.

## Before you start

- You have a clear feature spec (entities, fields, API endpoints, permissions)
- Docker stack is running (`make up-dev`)
- Previous migrations are applied (`make migrate-status-dev` shows current revision)

If you don't have a spec, write `docs/features/<feature>.md` first — it forces you to think through the decisions before touching code.

---

## Step 1 — Migration (Alembic)

Create `backend/migrations/versions/000N_<description>.py`:

```python
"""create <table>

Revision ID: 000N
Revises: 000(N-1)
Create Date: ...
"""

from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000N"
down_revision: str = "000(N-1)"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "<table>",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),  # tenant scoping
        # ... fields
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_<table>"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_<table>_tenant_id", ondelete="CASCADE"),
        sa.CheckConstraint("<check>", name="ck_<table>_<check>"),
    )


def downgrade() -> None:
    op.drop_table("<table>")
```

**Rules:**
- Use UUID primary keys with `gen_random_uuid()` server default
- Every tenant-scoped table has `tenant_id uuid NOT NULL` + `ON DELETE CASCADE` FK
- Money stored as `int` in cents (`price_cents`), never float
- Enums stored as `text` with a `CHECK` constraint (easier to migrate than Postgres ENUM)
- Named constraints (`pk_*`, `fk_*`, `ck_*`, `uq_*`, `ix_*`) so Alembic doesn't generate random names
- Timestamps are `timestamptz`, server-defaulted to `now()`

Run the migration:

```bash
make migrate-up-dev
```

Verify it applied:
```bash
make migrate-status-dev     # shows current revision
make list-tables-dev        # shows all tables
```

---

## Step 2 — Domain entity (Layer 3)

`backend/app/domain/entities/<feature>.py`:

```python
"""Pydantic domain entity for <feature>."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class MemberStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


class Member(BaseModel):
    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    status: MemberStatus = MemberStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def can_renew(self) -> bool:
        """Pure business logic — no I/O."""
        return self.status in (MemberStatus.ACTIVE, MemberStatus.FROZEN)
```

**Rules:**
- This layer **must not** import from `adapters/`, `services/`, or `api/`
- No SQLAlchemy, no FastAPI, no boto3 — pure Python + Pydantic
- Put pure business logic here (`can_renew`, `is_expired`, `display_name`)
- StrEnums for status fields

Add domain exceptions to `backend/app/domain/exceptions.py`:

```python
class MemberNotFoundError(AppError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Member not found: {identifier}", "MEMBER_NOT_FOUND")
```

Then map the error code to an HTTP status in `backend/app/api/error_handler.py`:

```python
_STATUS_MAP["MEMBER_NOT_FOUND"] = 404
```

---

## Step 3 — ORM model (Layer 4)

`backend/app/adapters/storage/postgres/<feature>/models.py`:

```python
"""SQLAlchemy ORM model for the ``<table>`` table."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.adapters.storage.postgres.database import Base


class MemberORM(Base):
    __tablename__ = "members"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_members_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'frozen', 'cancelled')", name="ck_members_status"),
    )
```

Register it in `backend/app/adapters/storage/postgres/__init__.py`:

```python
from app.adapters.storage.postgres.member.models import MemberORM

__all__ = [
    "Base",
    "MemberORM",
    # ...
]
```

---

## Step 4 — Repository (Layer 4)

`backend/app/adapters/storage/postgres/<feature>/repositories.py`:

```python
"""Repository for the ``<table>`` table."""

from __future__ import annotations
from typing import TYPE_CHECKING
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.adapters.storage.postgres.member.models import MemberORM
from app.domain.entities.member import Member, MemberStatus
from app.domain.exceptions import MemberNotFoundError

if TYPE_CHECKING:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: MemberORM) -> Member:
    return Member(
        id=orm.id,
        tenant_id=orm.tenant_id,
        first_name=orm.first_name,
        last_name=orm.last_name,
        status=MemberStatus(orm.status),
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class MemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: UUID, first_name: str, last_name: str) -> Member:
        orm = MemberORM(tenant_id=tenant_id, first_name=first_name, last_name=last_name)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_domain(orm)

    async def find_by_id(self, member_id: UUID, *, tenant_id: UUID) -> Member | None:
        """Tenant-scoped by construction."""
        result = await self._session.execute(
            select(MemberORM).where(
                MemberORM.id == member_id,
                MemberORM.tenant_id == tenant_id,
            ),
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_by_tenant(self, tenant_id: UUID, *, limit: int = 50, offset: int = 0) -> list[Member]:
        result = await self._session.execute(
            select(MemberORM)
            .where(MemberORM.tenant_id == tenant_id)
            .order_by(MemberORM.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [_to_domain(orm) for orm in result.scalars()]

    async def update(self, member_id: UUID, *, tenant_id: UUID, **fields) -> Member:
        await self._session.execute(
            update(MemberORM)
            .where(MemberORM.id == member_id, MemberORM.tenant_id == tenant_id)
            .values(**fields),
        )
        await self._session.flush()
        result = await self._session.execute(
            select(MemberORM).where(MemberORM.id == member_id, MemberORM.tenant_id == tenant_id),
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            raise MemberNotFoundError(str(member_id))
        await self._session.refresh(orm)
        return _to_domain(orm)
```

**Rules:**
- Return domain entities (Pydantic), never ORM objects
- Every query is **tenant-scoped** via `WHERE tenant_id = ?`
- Repository is **not** responsible for transactions — pass in the session, let the service commit
- Catch `IntegrityError` and convert to domain exceptions (`AlreadyExistsError`, etc.)
- Never leak SQLAlchemy types across the layer boundary

---

## Step 5 — Service (Layer 2)

`backend/app/services/<feature>_service.py`:

```python
"""Member service — orchestrates member CRUD with business rules."""

from __future__ import annotations
from typing import TYPE_CHECKING
from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.domain.entities.member import Member, MemberStatus
from app.domain.exceptions import InsufficientPermissionsError, MemberNotFoundError

if TYPE_CHECKING:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.security import TokenPayload


class MemberService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MemberRepository(session)

    async def create_member(self, *, caller: TokenPayload, first_name: str, last_name: str) -> Member:
        """Create a member in the caller's tenant."""
        self._require_staff_or_above(caller)
        tenant_id = self._resolve_tenant_id(caller)

        member = await self._repo.create(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
        )
        await self._session.commit()
        return member

    async def freeze_member(self, *, caller: TokenPayload, member_id: UUID) -> Member:
        self._require_staff_or_above(caller)
        tenant_id = self._resolve_tenant_id(caller)

        existing = await self._repo.find_by_id(member_id, tenant_id=tenant_id)
        if not existing:
            raise MemberNotFoundError(str(member_id))

        updated = await self._repo.update(member_id, tenant_id=tenant_id, status=MemberStatus.FROZEN.value)
        await self._session.commit()
        return updated

    # ── Private helpers ──────────────────────────────────────────

    @staticmethod
    def _require_staff_or_above(caller: TokenPayload) -> None:
        allowed = {"super_admin", "owner", "staff"}
        if caller.role not in allowed:
            raise InsufficientPermissionsError()

    @staticmethod
    def _resolve_tenant_id(caller: TokenPayload) -> UUID:
        """super_admin may act on any tenant; others are scoped to their own."""
        from uuid import UUID as UUIDType
        if caller.tenant_id is None:
            raise InsufficientPermissionsError()
        return UUIDType(caller.tenant_id)
```

**Rules:**
- **All business logic** lives here — permission checks, tenant scoping, trial checks, limit enforcement
- Services own the transaction — `await self._session.commit()` at the end of a command
- Services call **repository interfaces** — never raw SQL
- Raise domain exceptions — the error handler converts them to HTTP
- Private helpers (`_require_*`, `_resolve_*`) are static where they don't touch state

---

## Step 6 — API routes (Layer 1)

### Schemas

`backend/app/api/v1/<feature>/schemas.py`:

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from app.domain.entities.member import MemberStatus


class CreateMemberRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    model_config = {
        "json_schema_extra": {
            "examples": [{"first_name": "דני", "last_name": "פופוב"}],
        }
    }


class MemberResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    first_name: str
    last_name: str
    status: MemberStatus
    created_at: datetime
    updated_at: datetime
```

### Router

`backend/app/api/v1/<feature>/router.py`:

```python
"""Member routes."""

from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
from fastapi import APIRouter, Depends, status
from app.api.dependencies.auth import get_current_user, require_role
from app.api.dependencies.database import get_session
from app.api.v1.members.schemas import CreateMemberRequest, MemberResponse
from app.core.security import TokenPayload
from app.domain.entities.user import Role
from app.services.member_service import MemberService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

require_staff = require_role(Role.SUPER_ADMIN, Role.OWNER, Role.STAFF)


def _get_service(session: AsyncSession = Depends(get_session)) -> MemberService:
    return MemberService(session)


def _to_response(member) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        first_name=member.first_name,
        last_name=member.last_name,
        status=member.status,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: CreateMemberRequest,
    caller: TokenPayload = Depends(require_staff),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.create_member(
        caller=caller,
        first_name=body.first_name,
        last_name=body.last_name,
    )
    return _to_response(member)


@router.post("/{member_id}/freeze", response_model=MemberResponse)
async def freeze_member(
    member_id: UUID,
    caller: TokenPayload = Depends(require_staff),
    service: MemberService = Depends(_get_service),
) -> MemberResponse:
    member = await service.freeze_member(caller=caller, member_id=member_id)
    return _to_response(member)
```

Register in `backend/app/api/v1/router.py`:

```python
from app.api.v1.members.router import router as members_router

v1_router.include_router(
    members_router,
    prefix="/members",
    tags=["Members"],
    dependencies=api_rate_limit,  # applies 60/min/user rate limit
)
```

**Rules:**
- Routes are **thin** — parse HTTP → call service → format response. No logic.
- Permission gates go on the route via `Depends(require_role(...))`
- Status transitions are **explicit commands** (`/freeze`, `/unfreeze`, `/cancel`), not PATCH with `status`
- Rate limit is applied at the router inclusion level (not per-route)
- Every router gets tagged for Swagger grouping

---

## Step 7 — Tests

Three tiers: unit (domain logic), integration (repo against real Postgres), e2e (full HTTP via TestClient).

### Unit — `backend/tests/unit/test_member_entity.py`

```python
from datetime import UTC, datetime
from uuid import uuid4
from app.domain.entities.member import Member, MemberStatus


def _make(**overrides) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(), tenant_id=uuid4(), first_name="Dani", last_name="Popov",
        created_at=now, updated_at=now, **overrides,
    )


def test_active_member_can_renew() -> None:
    assert _make(status=MemberStatus.ACTIVE).can_renew() is True


def test_cancelled_member_cannot_renew() -> None:
    assert _make(status=MemberStatus.CANCELLED).can_renew() is False
```

### Integration — `backend/tests/integration/test_member_repo.py`

Use the `session` fixture from `conftest.py`. The test DB is cleaned between tests except for reference data (`saas_plans`, `alembic_version`).

```python
import pytest
from app.adapters.storage.postgres.member.repositories import MemberRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository


@pytest.fixture
def repo(session) -> MemberRepository:
    return MemberRepository(session)


@pytest.fixture
async def tenant(session):
    plan = await SaasPlanRepository(session).find_default()
    return await TenantRepository(session).create(
        slug="test-gym", name="Test Gym", saas_plan_id=plan.id,
    )


async def test_create_member(repo, tenant) -> None:
    member = await repo.create(tenant_id=tenant.id, first_name="Dani", last_name="Popov")
    assert member.tenant_id == tenant.id
    assert member.first_name == "Dani"
```

### E2E — `backend/tests/e2e/test_members.py`

Use the `client` + `auth_headers` fixtures from `conftest.py`. These give you a TestClient with a seeded super_admin.

```python
from fastapi.testclient import TestClient


def test_create_member(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/members",
        headers=auth_headers,
        json={"first_name": "Dani", "last_name": "Popov"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["first_name"] == "Dani"
    assert data["status"] == "active"


def test_non_staff_cannot_create_member(client: TestClient) -> None:
    # Create a sales token — should be 403
    from app.core.security import create_access_token
    import os
    token = create_access_token(
        user_id="...", role="sales", tenant_id="...",
        secret_key=os.environ["APP_SECRET_KEY"],
    )
    resp = client.post(
        "/api/v1/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "x", "last_name": "y"},
    )
    assert resp.status_code == 403
```

**Always test:**
- Happy path (create, list, get, update, delete)
- Permission boundaries (each role attempting the action)
- Not-found cases (404)
- Tenant isolation (user from tenant A can't see tenant B's data)
- SQL injection / XSS in user-provided strings
- Rate limiting (if the endpoint has a strict limit)

---

## Step 8 — Verify + commit

```bash
# Lint + format
uv run ruff check .
uv run ruff format --check .

# Run all tests
make test-backend-all-dev

# If all green → commit
git add ...
git commit -m "Add <feature> CRUD"
```

Verify the routes show up in Swagger at `http://localhost:8000/docs` — they should be grouped under the feature tag you added.

---

## Checklist

- [ ] Migration added and applied
- [ ] Domain entity + enum + pure business logic
- [ ] Domain exceptions registered in `error_handler.py`
- [ ] ORM model with named constraints + FK with `ON DELETE CASCADE`
- [ ] ORM registered in `storage/postgres/__init__.py`
- [ ] Repository with `_to_domain` translator, tenant-scoped queries
- [ ] Service with permission checks + `session.commit()`
- [ ] API router with thin handlers, `require_role` gates, rate limit
- [ ] Router registered in `v1/router.py`
- [ ] Pydantic schemas with `json_schema_extra` examples
- [ ] Unit tests for domain logic
- [ ] Integration tests for the repository (tenant-scoped)
- [ ] E2E tests: happy path + permission boundaries + edge cases
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] All tests pass (`make test-backend-all-dev`)
- [ ] Feature doc created at `docs/features/<feature>.md`
- [ ] Swagger page at `/docs` shows the new endpoints
