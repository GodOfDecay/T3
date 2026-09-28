"""The Programme API (shared/routers/modernization_programme.py) — Track 3 Phase C item 7.

Guarding tests: a non-Code-Modernization project has no Programme (404); reading needs
artifact:view; writing needs project:update AND administering THIS project (a Project Admin of
another project is refused even holding the permission); a target equal to the legacy
repository is refused; another tenant sees nothing. Real database (`sdlc_product_test`).
"""
from __future__ import annotations

import json
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config.auth.jwt import create_access_token
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import modernization_ledger as ledger

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

LEGACY = "https://github.com/contoso/claimtrack-legacy"
TARGET = "https://github.com/contoso/claimtrack-modern"
READ = ["artifact:view"]
WRITE = ["artifact:view", "project:update"]


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


async def _project(org: str, bu: str, track: str) -> str:
    proj = str(_uuid.uuid4())
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text(
            "INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
            "VALUES (:i, :w, :t, :n, :tr)"), {"i": proj, "w": bu, "t": org, "n": f"P-{track}", "tr": track})
    return proj


@pytest.fixture
async def env():
    org, bu = str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Prog')"),
                        {"i": org, "s": f"prog-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    modern = await _project(org, bu, "modernization")
    green = await _project(org, bu, "greenfield")
    other = await _project(org, bu, "modernization")
    for proj in (modern, green):
        await grant_role("u-pa", proj, "project_admin", tenant_id=org, scope_kind="project")
        await grant_role("u-dev", proj, "developer", tenant_id=org, scope_kind="project")
    await grant_role("u-pa-other", other, "project_admin", tenant_id=org, scope_kind="project")
    await grant_role("u-pa-other", modern, "developer", tenant_id=org, scope_kind="project")
    return {"org": org, "bu": bu, "modern": modern, "green": green, "other": other}


def _as(env, user, perms, org=None):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=org or env["org"], permissions=perms)}


def _url(proj, tail):
    return f"/modernization-programme/{proj}/{tail}"


async def test_the_ledger_lists_modules_in_order_with_the_state_columns(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="u-arch",
                                     artifact=ledger.ArtifactRef("design_modernization", 1),
                                     modules=[{"module_id": "M-02", "legacy_path": "src/b"},
                                              {"module_id": "M-01", "legacy_path": "src/a"}])
    client, hdr = _as(env, "u-dev", READ)
    r = client.get(_url(env["modern"], "ledger"), headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["states"] == list(ledger.STATES)
    assert [m["moduleId"] for m in body["modules"]] == ["M-01", "M-02"]
    assert {m["state"] for m in body["modules"]} == {"designed"}


async def test_a_greenfield_project_has_no_programme(env):
    client, hdr = _as(env, "u-pa", WRITE)
    for tail in ("ledger", "repositories", "approval-settings"):
        assert client.get(_url(env["green"], tail), headers=hdr).status_code == 404, tail
    r = client.put(_url(env["green"], "repositories/legacy"), json={"url": LEGACY}, headers=hdr)
    assert r.status_code == 404


async def test_reading_needs_artifact_view(env):
    client, hdr = _as(env, "u-dev", [])
    assert client.get(_url(env["modern"], "ledger"), headers=hdr).status_code == 403


async def test_a_project_admin_names_both_repositories(env):
    client, hdr = _as(env, "u-pa", WRITE)
    r = client.put(_url(env["modern"], "repositories/legacy"), json={"url": LEGACY + ".git", "branch": "main"},
                   headers=hdr)
    assert r.status_code == 200, r.text
    assert (r.json()["url"], r.json()["kind"], r.json()["setBy"]) == (LEGACY, "github", "u-pa")
    assert client.put(_url(env["modern"], "repositories/target"), json={"url": TARGET}, headers=hdr).status_code == 200
    got = client.get(_url(env["modern"], "repositories"), headers=_as(env, "u-dev", READ)[1]).json()
    assert (got["legacy"]["url"], got["target"]["url"]) == (LEGACY, TARGET)


async def test_the_target_cannot_be_the_legacy_repository(env):
    client, hdr = _as(env, "u-pa", WRITE)
    client.put(_url(env["modern"], "repositories/legacy"), json={"url": LEGACY}, headers=hdr)
    r = client.put(_url(env["modern"], "repositories/target"), json={"url": LEGACY + "/"}, headers=hdr)
    assert r.status_code == 400 and "legacy" in r.json()["detail"]


async def test_an_unknown_role_is_refused(env):
    client, hdr = _as(env, "u-pa", WRITE)
    r = client.put(_url(env["modern"], "repositories/scratch"), json={"url": TARGET}, headers=hdr)
    assert r.status_code == 422


async def test_writing_needs_project_update(env):
    client, hdr = _as(env, "u-pa", READ)
    assert client.put(_url(env["modern"], "repositories/legacy"), json={"url": LEGACY},
                      headers=hdr).status_code == 403


async def test_a_project_admin_of_another_project_cannot_write_here(env):
    """Holds project:update and is a member here — but administers a DIFFERENT project."""
    client, hdr = _as(env, "u-pa-other", WRITE)
    assert client.get(_url(env["modern"], "repositories"), headers=hdr).status_code == 200
    r = client.put(_url(env["modern"], "repositories/legacy"), json={"url": LEGACY}, headers=hdr)
    assert r.status_code == 404
    r = client.put(_url(env["modern"], "approval-settings"), json={"fallbackMode": "after_sla", "policy": "strict"},
                   headers=hdr)
    assert r.status_code == 404
    async with get_db_session_for_tenant(env["org"]) as s:
        assert (await s.execute(text("SELECT count(*) FROM project_repositories WHERE project_id = :p"),
                                {"p": env["modern"]})).scalar() == 0
        assert (await s.execute(text("SELECT approval_policy FROM projects WHERE id = :p"),
                                {"p": env["modern"]})).scalar() == "standard"


async def test_approval_settings_round_trip_with_warnings(env):
    client, hdr = _as(env, "u-pa", WRITE)
    r = client.get(_url(env["modern"], "approval-settings"), headers=hdr)
    assert r.status_code == 200, r.text
    assert (r.json()["fallbackMode"], r.json()["policy"]) == ("always", "standard")
    assert any("1 Project Admin" in w for w in r.json()["warnings"])
    r = client.put(_url(env["modern"], "approval-settings"), json={"fallbackMode": "after_sla", "policy": "strict"},
                   headers=hdr)
    assert r.status_code == 200, r.text
    assert (r.json()["fallbackMode"], r.json()["policy"]) == ("after_sla", "strict")
    r = client.put(_url(env["modern"], "approval-settings"), json={"fallbackMode": "never", "policy": "strict"},
                   headers=hdr)
    assert r.status_code == 422


async def test_another_tenant_sees_nothing(env):
    other_org = str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Else')"),
                        {"i": other_org, "s": f"else-{other_org[:8]}"})
    client, hdr = _as(env, "u-pa", WRITE, org=other_org)
    assert client.get(_url(env["modern"], "repositories"), headers=hdr).status_code == 404
    assert client.put(_url(env["modern"], "repositories/legacy"), json={"url": LEGACY},
                      headers=hdr).status_code == 404
