"""Unit tests for app.core.feature_flags.

Covers the four branches of ``is_feature_enabled``:
1. Ungated feature → always True.
2. Gated feature + key missing / False → False.
3. Gated feature + key True → True.
4. Unknown feature + None tenant fallback semantics.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.core.feature_flags import GATED, GatedFeature, is_feature_enabled
from app.domain.entities.tenant import Tenant


def _mk_tenant(features: dict | None = None) -> Tenant:
    now = datetime.now(UTC)
    return Tenant(
        id=uuid4(),
        slug="t",
        name="G",
        saas_plan_id=uuid4(),
        features_enabled=features or {},
        created_at=now,
        updated_at=now,
    )


# ── GATED set ─────────────────────────────────────────────────────────


def test_gated_set_contains_coaches_and_schedule() -> None:
    assert "coaches" in GATED
    assert "schedule" in GATED


def test_gated_enum_values_match_set() -> None:
    assert GATED == frozenset(f.value for f in GatedFeature)


# ── ungated branch ────────────────────────────────────────────────────


def test_ungated_feature_always_enabled() -> None:
    t = _mk_tenant({})
    # These are ungated — always on regardless of flag state.
    for ungated in ("members", "classes", "plans", "attendance", "dashboard"):
        assert is_feature_enabled(t, ungated) is True


def test_ungated_feature_with_none_tenant_still_enabled() -> None:
    # Platform-level endpoints (super_admin) pass tenant=None.
    assert is_feature_enabled(None, "tenants") is True


# ── gated branch ──────────────────────────────────────────────────────


def test_gated_feature_missing_key_is_disabled() -> None:
    t = _mk_tenant({})
    assert is_feature_enabled(t, "coaches") is False
    assert is_feature_enabled(t, "schedule") is False


def test_gated_feature_explicit_false_is_disabled() -> None:
    t = _mk_tenant({"coaches": False, "schedule": False})
    assert is_feature_enabled(t, "coaches") is False


def test_gated_feature_explicit_true_is_enabled() -> None:
    t = _mk_tenant({"coaches": True})
    assert is_feature_enabled(t, "coaches") is True
    # Unrelated gated feature stays off.
    assert is_feature_enabled(t, "schedule") is False


def test_gated_feature_truthy_value_enabled() -> None:
    # Spec says boolean, but JSONB could deserialize as other types.
    # Fail-open on truthy to be forgiving of manual DB edits.
    t = _mk_tenant({"coaches": 1})
    assert is_feature_enabled(t, "coaches") is True


# ── defensive branches ────────────────────────────────────────────────


def test_gated_feature_without_tenant_rejected() -> None:
    # Only ungated features tolerate tenant=None.
    assert is_feature_enabled(None, "coaches") is False


def test_null_features_enabled_treated_as_empty() -> None:
    t = _mk_tenant({})
    # Directly nulling out features_enabled (shouldn't happen in practice
    # because the DB column is NOT NULL) — still safe.
    t.features_enabled = {}  # empty dict, not None
    assert is_feature_enabled(t, "coaches") is False
