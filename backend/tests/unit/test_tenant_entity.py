"""Unit tests for the Tenant domain entity's pure logic methods."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.tenant import Tenant, TenantStatus


def _make_tenant(*, status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    now = datetime.now(UTC)
    return Tenant(
        id=uuid4(),
        slug="test-gym",
        name="Test Gym",
        status=status,
        saas_plan_id=uuid4(),
        timezone="Asia/Jerusalem",
        currency="ILS",
        locale="he-IL",
        created_at=now,
        updated_at=now,
    )


def test_active_tenant_is_active() -> None:
    tenant = _make_tenant(status=TenantStatus.ACTIVE)
    assert tenant.is_active() is True


def test_trial_tenant_is_active() -> None:
    tenant = _make_tenant(status=TenantStatus.TRIAL)
    assert tenant.is_active() is True


def test_suspended_tenant_is_not_active() -> None:
    tenant = _make_tenant(status=TenantStatus.SUSPENDED)
    assert tenant.is_active() is False


def test_cancelled_tenant_is_not_active() -> None:
    tenant = _make_tenant(status=TenantStatus.CANCELLED)
    assert tenant.is_active() is False


def test_default_status_is_active() -> None:
    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid4(),
        slug="x",
        name="X",
        saas_plan_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    assert tenant.status == TenantStatus.ACTIVE


def test_default_timezone_currency_locale() -> None:
    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid4(),
        slug="x",
        name="X",
        saas_plan_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    assert tenant.timezone == "Asia/Jerusalem"
    assert tenant.currency == "ILS"
    assert tenant.locale == "he-IL"
    assert tenant.address_country == "IL"
