"""Restore, compare, staleness and provenance on the version store (migration 0068,
shared/services/version_lineage.py, shared/routers/version_lineage.py) — real database.

Guarding tests for Phase C (Development Plan §8.3): restore creates vM and never mutates vN;
the restorer cannot approve vM; a newer APPROVED input makes a version stale and a newer
draft does not; provenance is write-once; a fallback approval must carry a reason.
Runs on `sdlc_product_test` (backend/.env.test).
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from config.auth.jwt import create_access_token
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import version_lineage as lineage
from shared.services.artifact_versions import (
    ArtifactVersionError, publish_version, snapshot_stage_payload,
)

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

BA, BA2, PA = "u-ba-1", "u-ba-2", "u-pa-1"
BRIEF_1 = {"system_name": "ClaimTrack", "goal": "one"}
BRIEF_2 = {"system_name": "ClaimTrack", "goal": "two", "extra": [1, 2]}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def project():
    org, bu, proj = str(_uuid.uuid4()), str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Lineage')"),
                        {"i": org, "s": f"lin-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', 'modernization')"), {"i": proj, "w": bu, "t": org})
        for payload in (BRIEF_1, BRIEF_2):
            await snapshot_stage_payload(s, tenant_id=org, project_id=proj, stage="requirements_modernization",
                                         payload=payload, produced_by=BA)
    return {"org": org, "project": proj, "bu": bu}


async def _row(p, stage, version):
    async with get_db_session_for_tenant(p["org"]) as s:
        return (await s.execute(text(
            "SELECT version, status, payload, content_hash, produced_by, restored_from, restore_reason, built_from "
            "FROM artifact_versions WHERE project_id = :p AND stage = :s AND version = :v"),
            {"p": p["project"], "s": stage, "v": version})).mappings().one()


# ── restore ──────────────────────────────────────────────────────────────────

async def test_restore_creates_a_new_draft_and_never_touches_the_old_version(project):
    before = dict(await _row(project, "requirements_modernization", 1))
    async with get_db_session_for_tenant(project["org"]) as s:
        ref = await lineage.restore_version(s, tenant_id=project["org"], project_id=project["project"],
                                            stage="requirements_modernization", version=1, restorer=BA2,
                                            reason="v2 widened the scope by mistake")
    assert (ref.version, ref.status) == (3, "draft")
    restored = await _row(project, "requirements_modernization", 3)
    assert restored["payload"] == BRIEF_1 and restored["content_hash"] == before["content_hash"]
    assert (restored["restored_from"], restored["restore_reason"], restored["produced_by"]) == (
        1, "v2 widened the scope by mistake", BA2)
    assert dict(await _row(project, "requirements_modernization", 1)) == before


async def test_the_restorer_cannot_approve_their_own_restore(project):
    async with get_db_session_for_tenant(project["org"]) as s:
        await lineage.restore_version(s, tenant_id=project["org"], project_id=project["project"],
                                      stage="requirements_modernization", version=1, restorer=BA2, reason="back")
    with pytest.raises((ArtifactVersionError, DBAPIError)):
        async with get_db_session_for_tenant(project["org"]) as s:
            await publish_version(s, tenant_id=project["org"], project_id=project["project"],
                                  stage="requirements_modernization", version=3, published_by=BA2)
    assert (await _row(project, "requirements_modernization", 3))["status"] == "draft"


@pytest.mark.parametrize("version,reason,match", [
    (1, "  ", "a reason is required"),
    (2, "back", "already the newest version"),
    (9, "back", "does not exist"),
])
async def test_restore_refusals(project, version, reason, match):
    with pytest.raises(lineage.RestoreRefused, match=match):
        async with get_db_session_for_tenant(project["org"]) as s:
            await lineage.restore_version(s, tenant_id=project["org"], project_id=project["project"],
                                          stage="requirements_modernization", version=version, restorer=BA2,
                                          reason=reason)


# ── staleness ────────────────────────────────────────────────────────────────

async def _assessment_pinned_to(p, brief_version: int) -> int:
    async with get_db_session_for_tenant(p["org"]) as s:
        ref = await snapshot_stage_payload(
            s, tenant_id=p["org"], project_id=p["project"], stage="discovery", payload={"modules": []},
            produced_by=BA, built_from=[{"artifact": "migration_intent_payload", "stage": "requirements_modernization",
                                         "version": brief_version, "status": "published"}])
    return ref.version


async def test_a_newer_approved_input_makes_a_version_stale(project):
    async with get_db_session_for_tenant(project["org"]) as s:
        await publish_version(s, tenant_id=project["org"], project_id=project["project"],
                              stage="requirements_modernization", version=1, published_by=PA)
    await _assessment_pinned_to(project, 1)
    async with get_db_session_for_tenant(project["org"]) as s:
        assert await lineage.stale_inputs(s, project["project"], [{"stage": "requirements_modernization", "version": 1}]) == []
        await publish_version(s, tenant_id=project["org"], project_id=project["project"],
                              stage="requirements_modernization", version=2, published_by=PA)
    async with get_db_session_for_tenant(project["org"]) as s:
        stale = await lineage.stale_inputs(s, project["project"],
                                           [{"stage": "requirements_modernization", "version": 1,
                                             "artifact": "migration_intent_payload"}])
    assert stale == [{"stage": "requirements_modernization", "artifact": "migration_intent_payload",
                      "pinned": 1, "latest": 2}]


async def test_a_newer_draft_does_not_make_it_stale(project):
    """v2 exists as a DRAFT above the pinned, published v1: nobody accepted it, so not stale."""
    async with get_db_session_for_tenant(project["org"]) as s:
        await publish_version(s, tenant_id=project["org"], project_id=project["project"],
                              stage="requirements_modernization", version=1, published_by=PA)
        assert await lineage.stale_inputs(s, project["project"], [{"stage": "requirements_modernization", "version": 1}]) == []


# ── compare ──────────────────────────────────────────────────────────────────

def test_compare_names_every_added_removed_and_changed_leaf():
    assert lineage.compare_payloads(BRIEF_1, BRIEF_2) == [
        {"path": "extra[0]", "change": "added", "before": None, "after": 1},
        {"path": "extra[1]", "change": "added", "before": None, "after": 2},
        {"path": "goal", "change": "changed", "before": "one", "after": "two"},
    ]
    assert lineage.compare_payloads(BRIEF_2, BRIEF_1)[0]["change"] == "removed"
    assert lineage.compare_payloads(BRIEF_1, BRIEF_1) == []


def test_compare_marks_a_shortened_value():
    diff = lineage.compare_payloads({"a": "x"}, {"a": "y" * 500})
    assert diff[0]["after"].endswith("[260 more characters]")


# ── the database's own rules ─────────────────────────────────────────────────

async def test_provenance_is_write_once(project):
    v = await _assessment_pinned_to(project, 1)
    with pytest.raises(DBAPIError, match="frozen"):
        async with get_db_session_for_tenant(project["org"]) as s:
            await s.execute(text("UPDATE artifact_versions SET built_from = '[]'::jsonb "
                                 "WHERE project_id = :p AND stage = 'discovery' AND version = :v"),
                            {"p": project["project"], "v": v})


async def test_a_fallback_approval_must_carry_a_reason(project):
    with pytest.raises(DBAPIError, match="ck_artifact_versions_fallback_has_reason"):
        async with get_db_session_for_tenant(project["org"]) as s:
            await s.execute(text("UPDATE artifact_versions SET approved_as = 'fallback:project_admin' "
                                 "WHERE project_id = :p AND stage = 'requirements_modernization' AND version = 1"),
                            {"p": project["project"]})


# ── the routes ───────────────────────────────────────────────────────────────

def _client_for(p, user, perms):
    import process_api
    token = create_access_token(user_id=user, tenant_id=p["org"], permissions=perms)
    return TestClient(process_api.app), {"Authorization": f"Bearer {token}"}


async def _member(p, user, role):
    from shared.authz.grant import grant_role
    await grant_role(user, p["project"], role, tenant_id=p["org"], scope_kind="project")


async def test_the_routes_restore_compare_and_report_staleness(project):
    await _member(project, BA2, "ba")
    client, hdr = _client_for(project, BA2, ["run:create", "artifact:view"])
    base = f"/artifact-versions/{project['project']}/stages/requirements_modernization"
    assert client.post(f"{base}/versions/1/restore", json={"reason": ""}, headers=hdr).status_code == 422
    r = client.post(f"{base}/versions/1/restore", json={"reason": "undo v2"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert (r.json()["version"], r.json()["restoredFrom"]) == (3, 1)
    diff = client.get(f"{base}/compare", params={"from": 2, "to": 3}, headers=hdr).json()
    assert {d["path"] for d in diff["differences"]} == {"goal", "extra[0]", "extra[1]"}
    s = client.get(f"{base}/versions/3/staleness", headers=hdr).json()
    assert (s["pinned"], s["stale"]) == (False, False)


async def test_restoring_needs_run_create(project):
    await _member(project, BA2, "ba")
    client, hdr = _client_for(project, BA2, ["artifact:view"])
    r = client.post(f"/artifact-versions/{project['project']}/stages/requirements_modernization/versions/1/restore",
                    json={"reason": "undo"}, headers=hdr)
    assert r.status_code == 403


# ── what a page freeze pins ──────────────────────────────────────────────────

async def test_a_page_freeze_pins_what_the_turn_read(project, monkeypatch):
    from agents_orchestrator.modernization_common import versions
    from config import ws_helper

    ws_helper.set_tenant_id(project["org"]); ws_helper.set_project_id(project["project"])
    ws_helper.set_user_id(BA); ws_helper.set_orchestrator_run(False)
    try:
        versions.reset_built_from()
        versions.note_input(artifact="migration_intent_payload", stage="requirements_modernization",
                            version=1, status="published")
        v = await versions.freeze_version("discovery", {"modules": ["x"]})
    finally:
        versions.reset_built_from()
    row = await _row(project, "discovery", v)
    assert row["built_from"] == [{"artifact": "migration_intent_payload", "stage": "requirements_modernization",
                                  "version": 1, "status": "published"}]
