"""Central v1 API router — includes all feature routers under ``/api/v1``."""

from fastapi import APIRouter

from app.api.dependencies.rate_limit import api_rate_limit
from app.api.v1.auth.router import router as auth_router
from app.api.v1.tenants.router import router as tenants_router
from app.api.v1.users.router import router as users_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
v1_router.include_router(
    tenants_router,
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=api_rate_limit,
)
v1_router.include_router(users_router, prefix="/users", tags=["Users"], dependencies=api_rate_limit)
