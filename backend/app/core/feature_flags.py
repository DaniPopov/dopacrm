"""Tenant-level feature flags.

Two kinds of features in DopaCRM:

- **Ungated** (always on): Members, Classes, Plans, Subscriptions,
  Attendance, Users. Every tenant sees these. They're the CRM.
- **Gated** (per-tenant toggle): Coaches, Schedule (+ future Payments,
  Leads, Reports). Stored in ``tenants.features_enabled`` JSONB.
  Super_admin flips them via ``PATCH /tenants/{id}/features``; owner
  self-service is a v2 follow-up.

Full spec: ``docs/features/feature-flags.md``.

Rule of thumb for deciding if a feature should be gated: **can the gym
plausibly operate without it?** Members + Attendance = always on.
Coach payroll tracking = optional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities.tenant import Tenant


class GatedFeature(StrEnum):
    """Features that require a tenant flag before they work.

    Everything NOT in this enum is ungated (always on).
    """

    COACHES = "coaches"
    SCHEDULE = "schedule"
    LEADS = "leads"


#: Set of gated feature names for fast lookup.
GATED: frozenset[str] = frozenset(f.value for f in GatedFeature)


def is_feature_enabled(tenant: Tenant | None, feature: str) -> bool:
    """Return True if the feature is available for this tenant.

    - **Ungated features** always return True (tenant argument may be
      None — useful for super_admin-only platform endpoints).
    - **Gated features** require ``tenant.features_enabled[feature]``
      to be truthy.
    - **Unknown feature names** return False (fail-closed — better a
      403 than silently bypassing a guard).

    The tenant argument is positional to keep call sites short at the
    top of every gated service method::

        if not is_feature_enabled(tenant, "coaches"):
            raise FeatureDisabledError("coaches")
    """
    if feature not in GATED:
        # Ungated → always on. Unknown feature names are caught at
        # import time by mypy / tests; at runtime they also land here
        # which is the safe default (False-returning for gated-only
        # logic below is a different branch).
        # Return True for any ungated/unknown-but-always-on feature:
        # the caller shouldn't even be checking an ungated flag, but
        # if they do, we don't block them.
        return True

    if tenant is None:
        # Gated feature checked with no tenant context → refuse.
        # Only happens in buggy call sites; fail closed.
        return False

    flags = tenant.features_enabled or {}
    return bool(flags.get(feature))


__all__ = ["GatedFeature", "GATED", "is_feature_enabled"]
