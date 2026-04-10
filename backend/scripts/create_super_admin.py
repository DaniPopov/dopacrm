"""Seed script: create the platform super_admin user.

Reads ``SEED_EMAIL`` and ``SEED_PASSWORD`` from environment variables and
creates a row in ``users`` with ``role=super_admin`` and ``tenant_id=NULL``
(platform-level, not scoped to any gym).

Idempotent: if a super_admin with this email already exists, the script
exits 0 without changes.

Usage (from project root, against a running dev stack):

    SEED_EMAIL=admin@dopacrm.com SEED_PASSWORD=... \\
        make seed-super-admin

Or directly inside the backend container:

    docker compose -f docker-compose.dev.yml exec \\
        -e SEED_EMAIL=... -e SEED_PASSWORD=... \\
        backend python -m scripts.create_super_admin
"""

from __future__ import annotations

import asyncio
import os
import sys

from app.adapters.storage.postgres.database import async_session_factory
from app.adapters.storage.postgres.user.repositories import UserRepository
from app.core.logger import get_logger
from app.core.security import hash_password
from app.domain.entities.user import Role
from app.domain.exceptions import UserAlreadyExistsError

logger = get_logger("scripts.create_super_admin")


async def _create_super_admin(email: str, password: str) -> None:
    """Insert (or skip) the platform super_admin row."""
    password_hash = hash_password(password)
    async with async_session_factory() as session:
        user_repo = UserRepository(session)

        existing = await user_repo.find_by_email(email, tenant_id=None)
        if existing is not None:
            logger.info(
                "super_admin_already_exists",
                email=email,
                user_id=str(existing.id),
            )
            return

        try:
            user = await user_repo.create(
                email=email,
                role=Role.SUPER_ADMIN,
                tenant_id=None,
                password_hash=password_hash,
            )
            await session.commit()
        except UserAlreadyExistsError:
            # Race: another process inserted the row between our check
            # and our insert. That's fine — the row exists, we're done.
            logger.info("super_admin_already_exists_race", email=email)
            return

        logger.info(
            "super_admin_created",
            email=email,
            user_id=str(user.id),
        )


def main() -> int:
    """Read env vars, validate, and run the async seed flow."""
    email = os.environ.get("SEED_EMAIL")
    password = os.environ.get("SEED_PASSWORD")

    if not email or not password:
        sys.stderr.write(
            "Error: SEED_EMAIL and SEED_PASSWORD must be set in the environment.\n"
            "Example: SEED_EMAIL=admin@example.com SEED_PASSWORD=secret "
            "make seed-super-admin\n"
        )
        return 1

    asyncio.run(_create_super_admin(email, password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
