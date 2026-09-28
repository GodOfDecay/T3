"""Dependency and Risk reads the Migration Intent brief through `read_upstream`, and the read
is RECORDED — against a real database, with controls (Lessons R4).

Before Phase B the page chat read the brief straight off `artifact_versions`, so a published
brief was used but no `artifact_consumptions` row said so, and "what did this assessment
build on" had no answer. And when publication was enforced and nothing was approved, the
agent got nothing at all — indistinguishable from "no brief was ever written".

Runs on `sdlc_product_test` (backend/.env.test). Real rows, real RLS, real publication.
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

from agents_orchestrator.modernization_common.standalone import upstream_from_pages
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.models.artifacts import MigrationIntentArtifact
from shared.services.artifact_versions import publish_version, snapshot_stage_payload

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

PRODUCER, APPROVER, READER = "ba-producer@example.com", "ba-approver@example.com", "ba-reader@example.com"
BRIEF = MigrationIntentArtifact(system_name="ClaimTrack", goal="Leave the Dallas data centre.").model_dump()


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def project():
    org, bu, proj = str(_uuid.uuid4()), str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Upstream Pages')"),
                        {"i": org, "s": f"upg-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack Modernization', 'modernization')"),
                        {"i": proj, "w": bu, "t": org})
        await snapshot_stage_payload(s, tenant_id=org, project_id=proj, stage="requirements_modernization",
                                     payload=BRIEF, produced_by=PRODUCER)
        await s.commit()
    return {"org": org, "project": proj}


async def _enforce(p: dict, on: bool) -> None:
    async with get_db_session_for_tenant(p["org"]) as s:
        await s.execute(text("UPDATE projects SET enforce_artifact_publication = :on WHERE id = :p"),
                        {"on": on, "p": p["project"]})
        await s.commit()


async def _publish(p: dict) -> None:
    async with get_db_session_for_tenant(p["org"]) as s:
        await publish_version(s, tenant_id=p["org"], project_id=p["project"], stage="requirements_modernization",
                              version=1, published_by=APPROVER)
        await s.commit()


async def _consumptions(p: dict) -> list[dict]:
    async with get_db_session_for_tenant(p["org"]) as s:
        rows = (await s.execute(text(
            "SELECT producing_stage, version, consumer_stage, consumed_by FROM artifact_consumptions "
            "WHERE project_id = :p"), {"p": p["project"]})).mappings().all()
    return [dict(r) for r in rows]


async def _read(p: dict) -> str:
    return await upstream_from_pages(p["project"], p["org"], "discovery", consumed_by=READER)


async def test_a_published_brief_is_read_and_the_read_is_recorded(project):
    await _publish(project)
    context = await _read(project)
    assert "Migration-intent brief v1 (approved)" in context
    assert "ClaimTrack" in context
    assert await _consumptions(project) == [{
        "producing_stage": "requirements_modernization", "version": 1,
        "consumer_stage": "discovery", "consumed_by": READER,
    }]


async def test_enforced_and_nothing_approved_says_so_and_uses_no_draft(project):
    """The removal control for the test above: take publication away and the brief must
    NOT arrive — and the agent must be told why, not handed an empty string."""
    await _enforce(project, True)
    context = await _read(project)
    assert "none approved yet" in context
    assert "ClaimTrack" not in context
    assert await _consumptions(project) == []


async def test_unenforced_draft_is_labelled_a_draft_and_not_recorded(project):
    context = await _read(project)
    assert "Migration-intent brief v1 (draft, not yet approved)" in context
    assert await _consumptions(project) == []


async def test_another_tenant_reads_nothing_of_it(project):
    """RLS: the same project id under another tenant's session finds no brief."""
    await _publish(project)
    other = str(_uuid.uuid4())
    assert await upstream_from_pages(project["project"], other, "discovery", consumed_by=READER) == ""


async def test_a_session_records_each_version_it_reads_once(project):
    """One consumption row per chat session and version — not one per turn (Phase B review)."""
    await _publish(project)
    for _ in range(3):
        await upstream_from_pages(project["project"], project["org"], "discovery", consumed_by=READER,
                                  consumer_session="s-1")
    assert len(await _consumptions(project)) == 1
    # A newer approved brief is a new read, recorded once more.
    async with get_db_session_for_tenant(project["org"]) as s:
        await snapshot_stage_payload(s, tenant_id=project["org"], project_id=project["project"],
                                     stage="requirements_modernization",
                                     payload={**BRIEF, "goal": "Leave Dallas by June."}, produced_by=PRODUCER)
        await publish_version(s, tenant_id=project["org"], project_id=project["project"],
                              stage="requirements_modernization", version=2, published_by=APPROVER)
    await upstream_from_pages(project["project"], project["org"], "discovery", consumed_by=READER,
                              consumer_session="s-1")
    assert sorted(r["version"] for r in await _consumptions(project)) == [1, 2]
