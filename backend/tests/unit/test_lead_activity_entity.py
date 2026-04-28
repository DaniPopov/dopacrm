"""Unit tests for the LeadActivity entity.

The entity is data-only — no methods. Tests just confirm the StrEnum
values match the DB CHECK constraint and that required fields raise.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.entities.lead_activity import LeadActivity, LeadActivityType


def test_type_enum_values_match_db_check_constraint() -> None:
    """The CHECK constraint in migration 0013 lists exactly these five.
    A drift here would let the entity accept a value the DB rejects."""
    assert {t.value for t in LeadActivityType} == {
        "call",
        "email",
        "note",
        "meeting",
        "status_change",
    }


def test_required_fields() -> None:
    """tenant_id / lead_id / type / note / created_at must be supplied."""
    with pytest.raises(ValidationError):
        # Missing every required field except id.
        LeadActivity(id=uuid4())  # type: ignore[call-arg]


def test_created_by_optional() -> None:
    """System-generated rows have created_by = None — must construct."""
    a = LeadActivity(
        id=uuid4(),
        tenant_id=uuid4(),
        lead_id=uuid4(),
        type=LeadActivityType.STATUS_CHANGE,
        note="new → contacted",
        created_by=None,
        created_at=datetime.now(UTC),
    )
    assert a.created_by is None
