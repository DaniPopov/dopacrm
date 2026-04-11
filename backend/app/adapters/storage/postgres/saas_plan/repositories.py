"""Repository for the ``saas_plans`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.adapters.storage.postgres.saas_plan.models import SaasPlanORM
from app.domain.entities.saas_plan import BillingPeriod, SaasPlan

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(orm: SaasPlanORM) -> SaasPlan:
    return SaasPlan(
        id=orm.id,
        code=orm.code,
        name=orm.name,
        price_cents=orm.price_cents,
        currency=orm.currency,
        billing_period=BillingPeriod(orm.billing_period),
        max_members=orm.max_members,
        max_staff_users=orm.max_staff_users,
        features=orm.features,
        is_public=orm.is_public,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class SaasPlanRepository:
    """Read-mostly repo for SaaS plans. Plans are seeded via migration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, plan_id: UUID) -> SaasPlan | None:
        result = await self._session.execute(
            select(SaasPlanORM).where(SaasPlanORM.id == plan_id),
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_by_code(self, code: str) -> SaasPlan | None:
        result = await self._session.execute(
            select(SaasPlanORM).where(SaasPlanORM.code == code),
        )
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def find_default(self) -> SaasPlan | None:
        """Return the default plan (``code='default'``) — used at signup."""
        return await self.find_by_code("default")

    async def list_public(self) -> list[SaasPlan]:
        """List publicly available plans (for signup screens)."""
        result = await self._session.execute(
            select(SaasPlanORM)
            .where(SaasPlanORM.is_public.is_(True))
            .order_by(SaasPlanORM.price_cents.asc()),
        )
        return [_to_domain(orm) for orm in result.scalars()]
