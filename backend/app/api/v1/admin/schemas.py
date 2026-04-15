"""Schemas for platform-admin-only endpoints (``/api/v1/admin/...``)."""

from __future__ import annotations

from pydantic import BaseModel


class PlatformStatsResponse(BaseModel):
    """Aggregate counts across every tenant on the platform.

    Powers the super_admin dashboard (AdminDashboard.tsx on the frontend).
    """

    total_tenants: int
    active_tenants: int
    new_tenants_this_month: int
    total_users: int
    total_members: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_tenants": 12,
                    "active_tenants": 10,
                    "new_tenants_this_month": 3,
                    "total_users": 45,
                    "total_members": 387,
                }
            ]
        }
    }
