"""Postgres adapter package.

Re-exports the SQLAlchemy DeclarativeBase plus every ORM class so Alembic's
``env.py`` can import them all from one place and pick up the full
metadata for autogenerate.

Adding a new entity? Create the folder + ``models.py`` then re-export the
ORM class here.
"""

from app.adapters.storage.postgres.class_coach.models import ClassCoachORM
from app.adapters.storage.postgres.class_entry.models import ClassEntryORM
from app.adapters.storage.postgres.class_schedule_template.models import (
    ClassScheduleTemplateORM,
)
from app.adapters.storage.postgres.class_session.models import ClassSessionORM
from app.adapters.storage.postgres.coach.models import CoachORM
from app.adapters.storage.postgres.database import Base, async_session_factory, get_engine
from app.adapters.storage.postgres.gym_class.models import GymClassORM
from app.adapters.storage.postgres.lead.models import LeadORM
from app.adapters.storage.postgres.lead_activity.models import LeadActivityORM
from app.adapters.storage.postgres.member.models import MemberORM
from app.adapters.storage.postgres.membership_plan.models import (
    MembershipPlanORM,
    PlanEntitlementORM,
)
from app.adapters.storage.postgres.refresh_token.models import RefreshTokenORM
from app.adapters.storage.postgres.saas_plan.models import SaasPlanORM
from app.adapters.storage.postgres.subscription.models import (
    SubscriptionEventORM,
    SubscriptionORM,
)
from app.adapters.storage.postgres.tenant.models import TenantORM
from app.adapters.storage.postgres.user.models import UserORM

__all__ = [
    "Base",
    "ClassCoachORM",
    "ClassEntryORM",
    "ClassScheduleTemplateORM",
    "ClassSessionORM",
    "CoachORM",
    "GymClassORM",
    "LeadActivityORM",
    "LeadORM",
    "MemberORM",
    "MembershipPlanORM",
    "PlanEntitlementORM",
    "RefreshTokenORM",
    "SaasPlanORM",
    "SubscriptionEventORM",
    "SubscriptionORM",
    "TenantORM",
    "UserORM",
    "async_session_factory",
    "get_engine",
]
