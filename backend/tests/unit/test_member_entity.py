"""Unit tests for the Member domain entity's pure logic methods."""

from datetime import UTC, date, datetime
from uuid import uuid4

from app.domain.entities.member import Member, MemberStatus


def _make_member(status: MemberStatus = MemberStatus.ACTIVE) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(),
        tenant_id=uuid4(),
        first_name="Dana",
        last_name="Cohen",
        phone="+972-50-123-4567",
        status=status,
        join_date=date(2026, 4, 14),
        created_at=now,
        updated_at=now,
    )


def test_full_name_joins_first_and_last() -> None:
    m = _make_member()
    assert m.full_name == "Dana Cohen"


def test_is_active_for_active_status() -> None:
    assert _make_member(MemberStatus.ACTIVE).is_active() is True


def test_is_active_false_for_other_statuses() -> None:
    for s in (MemberStatus.FROZEN, MemberStatus.CANCELLED, MemberStatus.EXPIRED):
        assert _make_member(s).is_active() is False


def test_can_freeze_only_when_active() -> None:
    assert _make_member(MemberStatus.ACTIVE).can_freeze() is True
    for s in (MemberStatus.FROZEN, MemberStatus.CANCELLED, MemberStatus.EXPIRED):
        assert _make_member(s).can_freeze() is False


def test_can_unfreeze_only_when_frozen() -> None:
    assert _make_member(MemberStatus.FROZEN).can_unfreeze() is True
    for s in (MemberStatus.ACTIVE, MemberStatus.CANCELLED, MemberStatus.EXPIRED):
        assert _make_member(s).can_unfreeze() is False


def test_can_cancel_blocks_only_already_cancelled() -> None:
    for s in (MemberStatus.ACTIVE, MemberStatus.FROZEN, MemberStatus.EXPIRED):
        assert _make_member(s).can_cancel() is True
    assert _make_member(MemberStatus.CANCELLED).can_cancel() is False


def test_custom_fields_default_to_empty_dict() -> None:
    m = _make_member()
    assert m.custom_fields == {}


def test_email_and_gender_optional() -> None:
    m = _make_member()
    assert m.email is None
    assert m.gender is None
