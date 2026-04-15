"""Seed script: create a test gym + owner/staff/sales users.

Reads ``SLUG`` from the environment and spins up a ready-to-use test
tenant. Useful for:
- Smoke-testing a newly shipped feature under each role
- Reproducing a bug report by logging in as the role the customer uses
- Demoing the product without touching real data

What it creates (all idempotent — re-running is a no-op):
- Tenant: slug=``$SLUG``, status=``active`` (no trial — ready for use),
  default saas plan assigned, Hebrew-locale regional defaults.
- Three users in that tenant:
    owner@{slug}.test   role=owner
    staff@{slug}.test   role=staff
    sales@{slug}.test   role=sales
  All with password ``TestPass1!`` (8 chars, 1 upper, 1 special —
  passes the password complexity validator).

Usage (from project root, against a running dev stack):

    make seed-test-gym-dev SLUG=dopamineo

Then log in as any of the three users at http://localhost:5173/login
with password ``TestPass1!`` to see that role's view of the gym.

**Dev only.** Uses ``.test`` TLD (reserved by RFC 2606, never routable)
so the emails can't accidentally collide with real addresses.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from typing import TYPE_CHECKING

from app.adapters.storage.postgres.database import async_session_factory
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import (
    TenantAlreadyExistsError,
    TenantRepository,
)
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.logger import get_logger
from app.core.security import hash_password
from app.domain.entities.tenant import TenantStatus
from app.domain.entities.user import Role
from app.domain.exceptions import UserAlreadyExistsError

if TYPE_CHECKING:
    from uuid import UUID

logger = get_logger("scripts.seed_test_gym")

# Same regex the CreateTenantRequest schema enforces. Duplicated here
# (not imported) so this script has zero API-layer deps.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

TEST_PASSWORD = "TestPass1!"  # noqa: S105 — dev-only seed, never used in prod
SEED_ROLES: tuple[Role, ...] = (Role.OWNER, Role.STAFF, Role.SALES)


async def _seed(slug: str) -> None:
    """Create (or reuse) the tenant + owner/staff/sales users."""
    password_hash = hash_password(TEST_PASSWORD)

    async with async_session_factory() as session:
        tenant_repo = TenantRepository(session)
        user_repo = UserRepository(session)
        plan_repo = SaasPlanRepository(session)

        # 1. Tenant ───────────────────────────────────────────────────────
        tenant = await tenant_repo.find_by_slug(slug)
        if tenant is None:
            plan = await plan_repo.find_default()
            if plan is None:
                sys.stderr.write("Error: no default saas plan seeded. Run migrations first.\n")
                return

            try:
                tenant = await tenant_repo.create(
                    slug=slug,
                    name=f"{slug.title()} (test)",
                    saas_plan_id=plan.id,
                    status=TenantStatus.ACTIVE.value,
                )
            except TenantAlreadyExistsError:
                # Race: another run inserted it. Just fetch.
                tenant = await tenant_repo.find_by_slug(slug)
                if tenant is None:
                    raise
            logger.info("test_tenant_created", slug=slug, tenant_id=str(tenant.id))
        else:
            logger.info("test_tenant_already_exists", slug=slug, tenant_id=str(tenant.id))

        # 2. Users ────────────────────────────────────────────────────────
        await _ensure_users(user_repo, tenant_id=tenant.id, slug=slug, pwd_hash=password_hash)

        await session.commit()

    _print_summary(slug)


async def _ensure_users(
    user_repo: UserRepository, *, tenant_id: UUID, slug: str, pwd_hash: str
) -> None:
    """Create each seed role's user if missing."""
    for role in SEED_ROLES:
        email = f"{role.value}@{slug}.test"
        existing = await user_repo.find_by_email(email, tenant_id=tenant_id)
        if existing is not None:
            logger.info("test_user_already_exists", email=email, role=role.value)
            continue
        try:
            await user_repo.create(
                email=email,
                role=role,
                tenant_id=tenant_id,
                password_hash=pwd_hash,
                first_name=role.value.title(),
                last_name="Test",
            )
            logger.info("test_user_created", email=email, role=role.value)
        except UserAlreadyExistsError:
            logger.info("test_user_already_exists_race", email=email, role=role.value)


def _print_summary(slug: str) -> None:
    """Human-readable summary at the end so the dev can copy credentials."""
    print("")  # noqa: T201
    print(f"✅ Test gym ready: slug={slug!r}")  # noqa: T201
    print("")  # noqa: T201
    print("  Login at http://localhost:5173/login with any of:")  # noqa: T201
    for role in SEED_ROLES:
        print(f"    {role.value:6s}  →  {role.value}@{slug}.test  /  {TEST_PASSWORD}")  # noqa: T201
    print("")  # noqa: T201


def main() -> int:
    slug = os.environ.get("SLUG", "").strip().lower()
    if not slug:
        sys.stderr.write(
            "Error: SLUG must be set in the environment.\n"
            "Example: make seed-test-gym-dev SLUG=dopamineo\n"
        )
        return 1
    if not SLUG_PATTERN.match(slug):
        sys.stderr.write(
            f"Error: SLUG {slug!r} must be lowercase English letters, digits, "
            "and hyphens — no spaces, uppercase, or underscores.\n"
        )
        return 1

    asyncio.run(_seed(slug))
    return 0


if __name__ == "__main__":
    sys.exit(main())
