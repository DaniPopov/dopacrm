"""Integration tests for LeadRepository + LeadActivityRepository.

Real Postgres, real SQL. Covers CRUD, filter combinations, lost-reason
aggregation (case-insensitive collapse) and the count-by-status
aggregation that backs the Kanban headers + dashboard widget.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.adapters.storage.postgres.lead.repositories import LeadRepository
from app.adapters.storage.postgres.lead_activity.repositories import (
    LeadActivityRepository,
)
from app.adapters.storage.postgres.saas_plan.repositories import SaasPlanRepository
from app.adapters.storage.postgres.tenant.repositories import TenantRepository
from app.domain.entities.lead import LeadSource, LeadStatus
from app.domain.entities.lead_activity import LeadActivityType


@pytest.fixture
def repo(session) -> LeadRepository:
    return LeadRepository(session)


@pytest.fixture
def activity_repo(session) -> LeadActivityRepository:
    return LeadActivityRepository(session)


@pytest.fixture
def tenant_repo(session) -> TenantRepository:
    return TenantRepository(session)


@pytest.fixture
async def default_plan_id(session):
    plan = await SaasPlanRepository(session).find_default()
    assert plan is not None
    return plan.id


async def _mk_tenant(tenant_repo: TenantRepository, plan_id):
    return await tenant_repo.create(
        slug=f"t-{uuid4().hex[:8]}",
        name="Test Gym",
        saas_plan_id=plan_id,
    )


# ── Basic CRUD ────────────────────────────────────────────────────────


async def test_create_lead_defaults(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    lead = await repo.create(
        tenant_id=t.id,
        first_name="יעל",
        last_name="כהן",
        phone="+972-50-123-4567",
    )
    assert lead.tenant_id == t.id
    assert lead.status == LeadStatus.NEW
    assert lead.source == LeadSource.OTHER
    assert lead.assigned_to is None
    assert lead.lost_reason is None
    assert lead.converted_member_id is None
    assert lead.custom_fields == {}


async def test_find_by_id(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    created = await repo.create(
        tenant_id=t.id, first_name="A", last_name="B", phone="+1"
    )
    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.id == created.id


async def test_find_by_id_returns_none_for_missing(repo) -> None:
    assert await repo.find_by_id(uuid4()) is None


async def test_update_partial(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    lead = await repo.create(
        tenant_id=t.id, first_name="A", last_name="B", phone="+1"
    )
    updated = await repo.update(lead.id, notes="follow up tuesday")
    assert updated is not None
    assert updated.notes == "follow up tuesday"
    # Untouched fields unchanged.
    assert updated.first_name == "A"


async def test_update_status_accepts_enum_or_string(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    lead = await repo.create(
        tenant_id=t.id, first_name="A", last_name="B", phone="+1"
    )
    # Enum form
    out1 = await repo.update(lead.id, status=LeadStatus.CONTACTED)
    assert out1 is not None and out1.status == LeadStatus.CONTACTED
    # String form
    out2 = await repo.update(lead.id, status="trial")
    assert out2 is not None and out2.status == LeadStatus.TRIAL


# ── List filters ──────────────────────────────────────────────────────


async def test_list_filters_by_status(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    a = await repo.create(tenant_id=t.id, first_name="A", last_name="A", phone="+1")
    await repo.create(tenant_id=t.id, first_name="B", last_name="B", phone="+2")
    await repo.update(a.id, status=LeadStatus.CONTACTED)

    contacted = await repo.list_for_tenant(t.id, status=[LeadStatus.CONTACTED])
    assert len(contacted) == 1
    assert contacted[0].id == a.id

    new = await repo.list_for_tenant(t.id, status=[LeadStatus.NEW])
    assert len(new) == 1
    assert new[0].first_name == "B"


async def test_list_filters_by_source(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=t.id, first_name="A", last_name="A", phone="+1", source=LeadSource.WALK_IN
    )
    await repo.create(
        tenant_id=t.id, first_name="B", last_name="B", phone="+2", source=LeadSource.WEBSITE
    )

    walk_ins = await repo.list_for_tenant(t.id, source=[LeadSource.WALK_IN])
    assert {ld.first_name for ld in walk_ins} == {"A"}


async def test_list_search_matches_name_phone_email(
    repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(
        tenant_id=t.id, first_name="Yael", last_name="Cohen", phone="+972-50-111-1111"
    )
    await repo.create(
        tenant_id=t.id,
        first_name="David",
        last_name="Bar",
        phone="+972-50-222-2222",
        email="dav@x.com",
    )

    by_first = await repo.list_for_tenant(t.id, search="yael")
    assert len(by_first) == 1
    by_last = await repo.list_for_tenant(t.id, search="bar")
    assert len(by_last) == 1
    by_phone = await repo.list_for_tenant(t.id, search="111-1111")
    assert len(by_phone) == 1
    by_email = await repo.list_for_tenant(t.id, search="dav@")
    assert len(by_email) == 1


async def test_list_filters_cross_tenant_isolation(
    repo, tenant_repo, default_plan_id
) -> None:
    t1 = await _mk_tenant(tenant_repo, default_plan_id)
    t2 = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=t1.id, first_name="A", last_name="A", phone="+1")
    await repo.create(tenant_id=t2.id, first_name="B", last_name="B", phone="+2")

    t1_leads = await repo.list_for_tenant(t1.id)
    assert {ld.first_name for ld in t1_leads} == {"A"}


# ── count_by_status + count_*_since ───────────────────────────────────


async def test_count_by_status_aggregates(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    a = await repo.create(tenant_id=t.id, first_name="A", last_name="A", phone="+1")
    b = await repo.create(tenant_id=t.id, first_name="B", last_name="B", phone="+2")
    c = await repo.create(tenant_id=t.id, first_name="C", last_name="C", phone="+3")
    await repo.update(a.id, status=LeadStatus.CONTACTED)
    await repo.update(b.id, status=LeadStatus.CONTACTED)
    await repo.update(c.id, status=LeadStatus.LOST, lost_reason="x")

    counts = await repo.count_by_status(t.id)
    assert counts.get(LeadStatus.CONTACTED) == 2
    assert counts.get(LeadStatus.LOST) == 1
    assert LeadStatus.NEW not in counts  # repo returns only present statuses


async def test_count_created_since(repo, tenant_repo, default_plan_id) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    await repo.create(tenant_id=t.id, first_name="A", last_name="A", phone="+1")
    await repo.create(tenant_id=t.id, first_name="B", last_name="B", phone="+2")

    since = datetime.now(UTC) - timedelta(days=1)
    assert await repo.count_created_since(t.id, since=since) == 2

    future = datetime.now(UTC) + timedelta(days=1)
    assert await repo.count_created_since(t.id, since=future) == 0


# ── Lost-reason aggregation (case-insensitive collapse) ───────────────


async def test_top_lost_reasons_collapses_case_insensitively(
    repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    # Three "too expensive"s in different cases + one "wrong location".
    for variant in ("Too Expensive", "too expensive", "TOO EXPENSIVE"):
        ld = await repo.create(
            tenant_id=t.id, first_name="A", last_name="A", phone=str(uuid4())
        )
        await repo.update(ld.id, status=LeadStatus.LOST, lost_reason=variant)

    ld = await repo.create(
        tenant_id=t.id, first_name="B", last_name="B", phone=str(uuid4())
    )
    await repo.update(ld.id, status=LeadStatus.LOST, lost_reason="wrong location")

    since = datetime.now(UTC) - timedelta(days=30)
    rows = await repo.top_lost_reasons(t.id, since=since)
    assert len(rows) == 2
    top = rows[0]
    assert top.reason == "too expensive"
    assert top.count == 3
    assert rows[1].reason == "wrong location"
    assert rows[1].count == 1


async def test_top_lost_reasons_ignores_blank_and_null(
    repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    # NULL lost_reason
    a = await repo.create(tenant_id=t.id, first_name="A", last_name="A", phone="+1")
    await repo.update(a.id, status=LeadStatus.LOST, lost_reason=None)
    # Blank string lost_reason
    b = await repo.create(tenant_id=t.id, first_name="B", last_name="B", phone="+2")
    await repo.update(b.id, status=LeadStatus.LOST, lost_reason="   ")

    since = datetime.now(UTC) - timedelta(days=30)
    rows = await repo.top_lost_reasons(t.id, since=since)
    assert rows == []


# ── Activity repo ─────────────────────────────────────────────────────


async def test_activity_create_and_list(
    session, repo, activity_repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    lead = await repo.create(
        tenant_id=t.id, first_name="A", last_name="A", phone="+1"
    )

    a1 = await activity_repo.create(
        tenant_id=t.id,
        lead_id=lead.id,
        type=LeadActivityType.NOTE,
        note="first contact",
    )
    # Commit between inserts so Postgres ``now()`` (which freezes for
    # the txn) advances. Production writes are separate API requests =
    # separate txns; only the test needs this hint.
    await session.commit()

    a2 = await activity_repo.create(
        tenant_id=t.id,
        lead_id=lead.id,
        type=LeadActivityType.CALL,
        note="left voicemail",
    )
    await session.commit()

    rows = await activity_repo.list_for_lead(lead.id)
    # newest-first ordering
    assert [r.id for r in rows] == [a2.id, a1.id]


async def test_activity_list_isolated_per_lead(
    repo, activity_repo, tenant_repo, default_plan_id
) -> None:
    t = await _mk_tenant(tenant_repo, default_plan_id)
    a = await repo.create(tenant_id=t.id, first_name="A", last_name="A", phone="+1")
    b = await repo.create(tenant_id=t.id, first_name="B", last_name="B", phone="+2")

    await activity_repo.create(
        tenant_id=t.id, lead_id=a.id, type=LeadActivityType.NOTE, note="A"
    )
    await activity_repo.create(
        tenant_id=t.id, lead_id=b.id, type=LeadActivityType.NOTE, note="B"
    )

    a_rows = await activity_repo.list_for_lead(a.id)
    b_rows = await activity_repo.list_for_lead(b.id)
    assert [r.note for r in a_rows] == ["A"]
    assert [r.note for r in b_rows] == ["B"]
