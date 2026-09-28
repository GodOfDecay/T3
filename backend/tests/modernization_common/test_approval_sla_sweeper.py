"""The approval-SLA sweep (workers/approval_sla_sweeper.py, migration 0070) — Track 3 Phase C.

Guarding tests: a Track 3 draft past its stage's SLA notifies the project's Project Admins
(role-addressed, project-scoped) exactly ONCE; one inside its SLA, a published one, one on an
archived project and a Track 1 stage's draft are left alone. Real database (`sdlc_product_test`).
The sweep is cross-tenant, so every assertion filters to this test's own project.
"""
from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services.artifact_versions import snapshot_stage_payload
from shared.services.fallback_approval import _sla_hours
from workers.approval_sla_sweeper import ApprovalSlaSweeper

pytestmark = pytest.mark.usefixtures("purge_created_orgs")


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


async def _project(org: str, bu: str, track: str = "modernization") -> str:
    proj = str(_uuid.uuid4())
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', :tr)"), {"i": proj, "w": bu, "t": org, "tr": track})
    return proj


@pytest.fixture
async def env():
    org, bu = str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Sla')"),
                        {"i": org, "s": f"sla-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    return {"org": org, "bu": bu, "project": await _project(org, bu)}


async def _draft(org, project, stage="requirements_modernization"):
    async with get_db_session_for_tenant(org) as s:
        return (await snapshot_stage_payload(s, tenant_id=org, project_id=project, stage=stage,
                                             payload={"n": str(_uuid.uuid4())}, produced_by="u-ba")).version


async def _sweep(project, now):
    return [x for x in await ApprovalSlaSweeper().sweep_once(now=now) if x["project_id"] == project]


async def _bell(org, project):
    async with get_db_session_for_tenant(org) as s:
        return (await s.execute(text(
            "SELECT kind, recipient_role, recipient_scope_kind, recipient_scope_id::text AS scope, href, title "
            "FROM notifications WHERE tenant_id = CAST(:t AS uuid) AND project_id = CAST(:p AS uuid)"),
            {"t": org, "p": project})).mappings().all()


def _later(hours):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def test_a_draft_past_its_sla_notifies_the_project_admins_once(env):
    v = await _draft(env["org"], env["project"])
    sla = _sla_hours("requirements_modernization")
    sent = await _sweep(env["project"], _later(sla + 1))
    assert [(x["stage"], x["version"]) for x in sent] == [("requirements_modernization", v)]
    bell = await _bell(env["org"], env["project"])
    assert [(b["kind"], b["recipient_role"], b["recipient_scope_kind"], b["scope"]) for b in bell] == [
        ("approval_sla_passed", "project_admin", "project", env["project"])]
    assert bell[0]["href"] == f"/projects/{env['project']}/requirements-modernization"
    assert await _sweep(env["project"], _later(sla + 5)) == []
    assert len(await _bell(env["org"], env["project"])) == 1


async def test_a_draft_inside_its_sla_is_left_alone(env):
    await _draft(env["org"], env["project"])
    assert await _sweep(env["project"], _later(_sla_hours("requirements_modernization") - 1)) == []
    assert await _bell(env["org"], env["project"]) == []


async def test_a_published_version_is_left_alone(env):
    v = await _draft(env["org"], env["project"])
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text("UPDATE artifact_versions SET status = 'published', published_by = 'u-ba2', "
                             "published_at = now(), approved_as = 'owner' "
                             "WHERE project_id = :p AND version = :v"), {"p": env["project"], "v": v})
    assert await _sweep(env["project"], _later(1000)) == []


async def test_an_archived_project_is_left_alone(env):
    await _draft(env["org"], env["project"])
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text("UPDATE projects SET archived = true WHERE id = :p"), {"p": env["project"]})
    assert await _sweep(env["project"], _later(1000)) == []


async def test_a_track1_draft_is_left_alone(env):
    green = await _project(env["org"], env["bu"], "greenfield")
    await _draft(env["org"], green, stage="requirements")
    assert await _sweep(green, _later(1000)) == []
    assert await _bell(env["org"], green) == []


async def test_a_track3_stage_draft_on_another_track_is_left_alone(env):
    """The stage list alone is not the boundary: the project must be a Code Modernization one."""
    green = await _project(env["org"], env["bu"], "greenfield")
    await _draft(env["org"], green, stage="requirements_modernization")
    assert await _sweep(green, _later(1000)) == []


async def test_the_sla_is_the_stages_own(env, monkeypatch):
    """A stage with a longer SLA waits longer — the sweep reads it per stage."""
    from shared.services import fallback_approval
    monkeypatch.setattr(fallback_approval, "_sla_hours", lambda stage: 200)
    await _draft(env["org"], env["project"])
    assert await _sweep(env["project"], _later(100)) == []
    assert len(await _sweep(env["project"], _later(201))) == 1
