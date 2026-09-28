"""The Project Admin reach floor on Code Modernization agents (Track 3 research §12.2 rule 9).

The Project Admin is every Track 3 stage's fallback approver, so a role-level override may
not lower `project_admin` below owner on a Track 3 agent: the write refuses it (409), and the
resolver ignores such a row if one exists anyway. Track 1 agents and other roles are
unchanged. Real database (`sdlc_product_test`).
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config.auth.jwt import create_access_token
from shared.authz.agent_access import pa_floor_applies, resolve_involvement
from shared.db import get_db_session_for_tenant, get_db_session_superuser

pytestmark = pytest.mark.usefixtures("purge_created_orgs")


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def env():
    org, bu, proj = str(_uuid.uuid4()), str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Floor')"),
                        {"i": org, "s": f"floor-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', 'modernization')"), {"i": proj, "w": bu, "t": org})
    return {"org": org, "project": proj}


def _put(env, role, phase, involvement):
    import process_api
    return TestClient(process_api.app).put(
        f"/projects/{env['project']}/agent-access-overrides",
        headers={"Authorization": "Bearer " + create_access_token(
            user_id="u-org", tenant_id=env["org"], permissions=["admin:*"])},
        json={"role": role, "phase": phase, "involvement": involvement})


def test_the_floor_is_the_project_admin_on_track3_agents_only():
    assert pa_floor_applies("project_admin", "discovery")
    assert pa_floor_applies("project_admin", "documentation_modernization")
    assert not pa_floor_applies("project_admin", "requirements")
    assert not pa_floor_applies("project_admin", "security")
    assert not pa_floor_applies("ba", "requirements_modernization")


@pytest.mark.parametrize("involvement", ["none", "use", "primary"])
async def test_lowering_the_project_admin_on_a_track3_agent_is_refused(env, involvement):
    r = _put(env, "project_admin", "requirements_modernization", involvement)
    assert r.status_code == 409 and "fallback approver" in r.json()["detail"]
    async with get_db_session_for_tenant(env["org"]) as s:
        assert (await s.execute(text("SELECT count(*) FROM agent_access_overrides WHERE project_id = :p"),
                                {"p": env["project"]})).scalar() == 0


async def test_owner_for_the_project_admin_is_allowed(env):
    assert _put(env, "project_admin", "discovery", "owner").status_code == 200


async def test_other_roles_and_track1_agents_are_unchanged(env):
    assert _put(env, "ba", "requirements_modernization", "use").status_code == 200
    assert _put(env, "project_admin", "security", "use").status_code == 200


async def test_the_resolver_ignores_a_lowering_row_that_exists_anyway(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text(
            "INSERT INTO agent_access_overrides (id, tenant_id, project_id, role, phase, involvement, set_by) "
            "VALUES (CAST(:i AS uuid), CAST(:t AS uuid), :p, 'project_admin', :ph, 'none', 'legacy')"),
            {"i": str(_uuid.uuid4()), "t": env["org"], "p": env["project"], "ph": "strategy"})
        await s.execute(text(
            "INSERT INTO agent_access_overrides (id, tenant_id, project_id, role, phase, involvement, set_by) "
            "VALUES (CAST(:i AS uuid), CAST(:t AS uuid), :p, 'ba', :ph, 'none', 'legacy')"),
            {"i": str(_uuid.uuid4()), "t": env["org"], "p": env["project"], "ph": "requirements_modernization"})
    async with get_db_session_for_tenant(env["org"]) as s:
        pa = await resolve_involvement(s, tenant_id=env["org"], project_id=env["project"], role="project_admin",
                                       user_id="u-pa", agent_id="strategy", extra_agents=set())
        ba = await resolve_involvement(s, tenant_id=env["org"], project_id=env["project"], role="ba",
                                       user_id="u-ba", agent_id="requirements_modernization", extra_agents=set())
    assert (pa, ba) == ("owner", "none")
