"""Central v1 API router — includes all feature routers under ``/api/v1``."""

from fastapi import APIRouter

from app.api.dependencies.rate_limit import api_rate_limit
from app.api.v1.admin.router import router as admin_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.classes.router import router as classes_router
from app.api.v1.members.router import router as members_router
from app.api.v1.plans.router import router as plans_router
from app.api.v1.tenants.router import router as tenants_router
from app.api.v1.uploads.router import router as uploads_router
from app.api.v1.users.router import router as users_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
v1_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin"],
    dependencies=api_rate_limit,
)
v1_router.include_router(
    tenants_router,
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=api_rate_limit,
)
v1_router.include_router(
    uploads_router,
    prefix="/uploads",
    tags=["Uploads"],
    dependencies=api_rate_limit,
)
v1_router.include_router(users_router, prefix="/users", tags=["Users"], dependencies=api_rate_limit)
v1_router.include_router(
    members_router,
    prefix="/members",
    tags=["Members"],
    dependencies=api_rate_limit,
)
v1_router.include_router(
    classes_router,
    prefix="/classes",
    tags=["Classes"],
    dependencies=api_rate_limit,
)
v1_router.include_router(
    plans_router,
    prefix="/plans",
    tags=["Membership Plans"],
    dependencies=api_rate_limit,
)
