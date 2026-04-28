"""Unit tests for the Lead domain entity's pure logic methods.

Most of the value here is the ``can_transition_to`` matrix — the state
machine is the heart of the pipeline. We probe every legal + illegal
move so a future refactor of the matrix can't silently break the rules.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.lead import Lead, LeadSource, LeadStatus


def _make_lead(
    status: LeadStatus = LeadStatus.NEW,
    converted_member_id=None,
    lost_reason: str | None = None,
) -> Lead:
    now = datetime.now(UTC)
    return Lead(
        id=uuid4(),
        tenant_id=uuid4(),
        first_name="יעל",
        last_name="כהן",
        phone="+972-50-123-4567",
        email=None,
        source=LeadSource.WALK_IN,
        status=status,
        assigned_to=None,
        notes="Asked about boxing",
        lost_reason=lost_reason,
        converted_member_id=converted_member_id,
        custom_fields={},
        created_at=now,
        updated_at=now,
    )


# ── full_name + is_open ──────────────────────────────────────────────


def test_full_name_joins_first_and_last() -> None:
    assert _make_lead().full_name == "יעל כהן"


def test_is_open_for_new_contacted_trial() -> None:
    assert _make_lead(LeadStatus.NEW).is_open() is True
    assert _make_lead(LeadStatus.CONTACTED).is_open() is True
    assert _make_lead(LeadStatus.TRIAL).is_open() is True


def test_is_open_false_for_terminal_states() -> None:
    assert _make_lead(LeadStatus.CONVERTED, converted_member_id=uuid4()).is_open() is False
    assert _make_lead(LeadStatus.LOST, lost_reason="too expensive").is_open() is False


# ── State machine matrix ─────────────────────────────────────────────


# Every (current, target, expected) tuple. Encoded literally so a
# future change to the matrix forces an explicit test update.
@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        # FROM new — forward skips OK; lost OK; converted blocked everywhere
        (LeadStatus.NEW, LeadStatus.CONTACTED, True),
        (LeadStatus.NEW, LeadStatus.TRIAL, True),
        (LeadStatus.NEW, LeadStatus.LOST, True),
        (LeadStatus.NEW, LeadStatus.CONVERTED, False),
        (LeadStatus.NEW, LeadStatus.NEW, False),  # no-op
        # FROM contacted
        (LeadStatus.CONTACTED, LeadStatus.TRIAL, True),
        (LeadStatus.CONTACTED, LeadStatus.LOST, True),
        (LeadStatus.CONTACTED, LeadStatus.NEW, False),  # backward not allowed
        (LeadStatus.CONTACTED, LeadStatus.CONVERTED, False),
        (LeadStatus.CONTACTED, LeadStatus.CONTACTED, False),
        # FROM trial
        (LeadStatus.TRIAL, LeadStatus.CONTACTED, True),  # "trial didn't happen"
        (LeadStatus.TRIAL, LeadStatus.LOST, True),
        (LeadStatus.TRIAL, LeadStatus.NEW, False),
        (LeadStatus.TRIAL, LeadStatus.CONVERTED, False),
        (LeadStatus.TRIAL, LeadStatus.TRIAL, False),
        # FROM converted — terminal source
        (LeadStatus.CONVERTED, LeadStatus.NEW, False),
        (LeadStatus.CONVERTED, LeadStatus.CONTACTED, False),
        (LeadStatus.CONVERTED, LeadStatus.TRIAL, False),
        (LeadStatus.CONVERTED, LeadStatus.LOST, False),
        (LeadStatus.CONVERTED, LeadStatus.CONVERTED, False),
        # FROM lost — only reopen path
        (LeadStatus.LOST, LeadStatus.CONTACTED, True),
        (LeadStatus.LOST, LeadStatus.NEW, False),
        (LeadStatus.LOST, LeadStatus.TRIAL, False),
        (LeadStatus.LOST, LeadStatus.CONVERTED, False),
        (LeadStatus.LOST, LeadStatus.LOST, False),
    ],
)
def test_can_transition_to_matrix(
    current: LeadStatus, target: LeadStatus, expected: bool
) -> None:
    lead = _make_lead(current)
    if current == LeadStatus.CONVERTED:
        # Converted leads must carry a member id; build a real one.
        lead = _make_lead(current, converted_member_id=uuid4())
    if current == LeadStatus.LOST:
        lead = _make_lead(current, lost_reason="too expensive")
    assert lead.can_transition_to(target) is expected


def test_converted_is_never_a_legal_target() -> None:
    """The convert endpoint is the only path to ``converted``. The
    simple ``set_status`` route must reject it from any source."""
    for src in LeadStatus:
        lead = _make_lead(src)
        if src == LeadStatus.CONVERTED:
            lead = _make_lead(src, converted_member_id=uuid4())
        if src == LeadStatus.LOST:
            lead = _make_lead(src, lost_reason="too expensive")
        assert lead.can_transition_to(LeadStatus.CONVERTED) is False


# ── Default values ───────────────────────────────────────────────────


def test_custom_fields_defaults_to_empty_dict() -> None:
    assert _make_lead().custom_fields == {}


def test_source_and_status_default_via_pydantic() -> None:
    """Verify the entity-level defaults match the DB defaults."""
    now = datetime.now(UTC)
    lead = Lead(
        id=uuid4(),
        tenant_id=uuid4(),
        first_name="A",
        last_name="B",
        phone="+1",
        created_at=now,
        updated_at=now,
    )
    assert lead.source == LeadSource.OTHER
    assert lead.status == LeadStatus.NEW
