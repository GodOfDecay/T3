"""Approving a target design puts its modules on the ledger; the page's routes for it.

Real database (`sdlc_product_test`), through the real app. Guarding:
  - approval (an Architect who did not produce it) → every module `designed` with its patterns,
    contracts, ADRs and legacy path, the history entry naming the version;
  - the producer cannot approve, and nothing reaches the ledger;
  - a Project Admin approves as labelled fallback, with a reason;
  - D14 across commits: an id whose path changed is refused, the approval rolls back, the ledger
    is untouched;
  - re-approving a revision updates the rows and never moves one backwards;
  - recording writes nothing to the ledger (only approval does);
  - the packet, export and interface routes answer for this stage and are guarded like the rest.
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agents_orchestrator.modernization_common import legacy_code
from config.auth.jwt import create_access_token
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import modernization_ledger as ledger
from shared.services.artifact_versions import snapshot_stage_payload
from shared.models.artifacts import TargetDesignArtifact
from tests.design_modernization.claimtrack import build_repo, design_payload, stored_assessment

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "design_modernization"
APPROVE = [f"artifact:approve_{STAGE}", "artifact:view"]
PATHS = {m["id"]: m["path"] for m in stored_assessment()["modules"]}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def env():
    org, bu, modern, green = (str(_uuid.uuid4()) for _ in range(4))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseE')"),
                        {"i": org, "s": f"pe-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        for pid, track in ((modern, "modernization"), (green, "greenfield")):
            await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                                 "VALUES (:i, :w, :t, 'ClaimTrack', :tr)"), {"i": pid, "w": bu, "t": org, "tr": track})
    for user, role in (("u-arch", "architect"), ("u-arch2", "architect"), ("u-pa", "project_admin")):
        await grant_role(user, modern, role, tenant_id=org, scope_kind="project")
    await grant_role("u-arch2", green, "architect", tenant_id=org, scope_kind="project")
    return {"org": org, "modern": modern, "green": green}


def _design(**changes) -> dict:
    d = design_payload()
    d.update(changes)
    return TargetDesignArtifact(**d, system_name="ClaimTrack", module_paths=PATHS,
                                sources={"brief": {"version": 1, "status": "published"}}).model_dump(mode="json")


async def _draft(env, payload=None, produced_by="u-arch"):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage=STAGE,
                                             payload=payload or _design(), produced_by=produced_by)).version


def _client(env, user, perms=APPROVE):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=perms)}


def _publish(env, v, user, body=None):
    client, hdr = _client(env, user)
    return client.post(f"/artifact-versions/{env['modern']}/stages/{STAGE}/versions/{v}/publish",
                       json=body or {}, headers=hdr)


async def _ledger(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return {r.module_id: r for r in await ledger.list_modules(s, env["modern"])}


async def _status(env, v):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text("SELECT status FROM artifact_versions WHERE project_id = :p AND stage = :s "
                                     "AND version = :v"), {"p": env["modern"], "s": STAGE, "v": v})).scalar_one()


# ── approval → ledger ────────────────────────────────────────────────────────

async def test_approval_puts_every_module_on_the_ledger_as_designed(env):
    v = await _draft(env)
    assert await _ledger(env) == {}, "recording (a draft) writes nothing to the ledger"
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 200, r.text
    rows = await _ledger(env)
    assert sorted(rows) == ["M-01", "M-02", "M-03", "M-04", "M-05"]
    m2 = rows["M-02"]
    assert (m2.state, m2.module_name, m2.legacy_path, m2.tier, m2.risk_score) == (
        "designed", "claimtrack-web", "claimtrack-web", "llm_assisted", 56)
    assert (m2.patterns, m2.contract_ids, m2.adr_ids) == (["in_place_upgrade", "strangler_fig"], ["CT-01"],
                                                          ["ADR-03", "ADR-05"])
    assert m2.history[-1]["artifact"] == {"stage": "target_design_artifacts", "version": v}
    assert m2.history[-1]["by"] == "u-arch2"


async def test_the_producer_cannot_approve_and_nothing_reaches_the_ledger(env):
    v = await _draft(env)
    r = _publish(env, v, "u-arch")
    assert r.status_code == 403, r.text
    assert await _status(env, v) == "draft" and await _ledger(env) == {}


async def test_a_project_admin_approves_as_fallback_with_a_reason(env):
    v = await _draft(env)
    r = _publish(env, v, "u-pa", {"fallbackReason": "The architect is on leave"})
    assert r.status_code == 200, r.text
    assert r.json()["approvedAs"] == "fallback:project_admin"
    assert (await _ledger(env))["M-01"].state == "designed"


async def test_id_drift_across_commits_refuses_the_approval_and_rolls_it_back(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="u-arch2",
                                     artifact=ledger.ArtifactRef("target_design_artifacts", 1),
                                     modules=[{"module_id": "M-03", "module_name": "claimtrack-reports",
                                               "legacy_path": "claimtrack-reports", "patterns": ["keep"]}])
    v = await _draft(env)
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409, r.text
    assert "M-03 is claimtrack-reports on the ledger but claimtrack-batch in this design" in r.json()["detail"]
    assert await _status(env, v) == "draft"
    rows = await _ledger(env)
    assert sorted(rows) == ["M-03"] and rows["M-03"].patterns == ["keep"]


async def test_a_revised_design_updates_the_rows_and_never_moves_one_backwards(env):
    assert _publish(env, await _draft(env), "u-arch2").status_code == 200
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.plan_approved(s, project_id=env["modern"], module_id="M-01", wave="W1", ec_ids=["EC-01"],
                                   actor="u-arch2", artifact=ledger.ArtifactRef("strategy_artifacts", 1))
    revised = design_payload()
    revised["modules"][0]["patterns"] = ["in_place_upgrade", "branch_by_abstraction"]
    v2 = await _draft(env, TargetDesignArtifact(**revised, module_paths=PATHS).model_dump(mode="json"))
    r = _publish(env, v2, "u-arch2")
    assert r.status_code == 200, r.text
    rows = await _ledger(env)
    assert rows["M-01"].state == "sequenced" and rows["M-01"].patterns == ["in_place_upgrade", "branch_by_abstraction"]
    assert rows["M-01"].history[-1]["note"] == "design revised"


async def test_the_ledger_service_refuses_drift_on_its_own_terms(env):
    """The refusal belongs to the ledger, not to the route: a direct caller is refused too."""
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="a",
                                     artifact=ledger.ArtifactRef("target_design_artifacts", 1),
                                     modules=[{"module_id": "M-01", "legacy_path": "core"}])
    with pytest.raises(ledger.LedgerRefused, match="M-01 is core on the ledger but web"):
        async with get_db_session_for_tenant(env["org"]) as s:
            await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="a",
                                         artifact=ledger.ArtifactRef("target_design_artifacts", 2),
                                         modules=[{"module_id": "M-01", "legacy_path": "web/"}])


async def test_a_different_id_for_a_folder_the_ledger_holds_is_refused(env):
    """Review fix #8, the other direction: ledger M-03 is claimtrack-batch; a design calling that
    folder M-04 would give it a second row."""
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="a",
                                     artifact=ledger.ArtifactRef("target_design_artifacts", 1),
                                     modules=[{"module_id": "M-09", "legacy_path": "claimtrack-batch"}])
    v = await _draft(env)
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409, r.text
    assert "claimtrack-batch is M-09 on the ledger but M-03 in this design" in r.json()["detail"]
    assert sorted(await _ledger(env)) == ["M-09"]


async def test_a_trailing_slash_is_the_same_folder(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="a",
                                     artifact=ledger.ArtifactRef("target_design_artifacts", 1),
                                     modules=[{"module_id": "M-01", "legacy_path": "core/"}])
        rows = await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="a",
                                            artifact=ledger.ArtifactRef("target_design_artifacts", 2),
                                            modules=[{"module_id": "M-01", "legacy_path": "/core"}])
    assert rows[0].history[-1]["note"] == "design revised"


async def test_a_design_without_module_paths_is_not_approved(env):
    """Review fix #8: without paths the ledger cannot check ids, so nothing reaches it."""
    payload = _design()
    payload["module_paths"] = {k: v for k, v in payload["module_paths"].items() if k != "M-02"}
    v = await _draft(env, payload)
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409 and "where M-02 live" in r.json()["detail"], r.text
    assert await _status(env, v) == "draft" and await _ledger(env) == {}


# ── the page's routes ────────────────────────────────────────────────────────

def _get(env, path, user="u-arch2", perms=("artifact:view",)):
    client, hdr = _client(env, user, list(perms))
    return client.get(path, headers=hdr)


async def test_the_packet_route_hands_the_design_to_migration_strategy(env):
    v = await _draft(env)
    body = _get(env, f"/projects/{env['modern']}/modernization/target-architecture/versions/{v}/packet").json()
    assert body["ok"] is True, body
    assert body["packet"]["agent_id"] == STAGE and body["packet"]["artifact"] == "target_design_artifacts"
    assert "module_paths" not in body["packet"]["payload"]  # the page's, not the hand-over's
    bad = await _draft(env, {**_design(), "modules": []})
    body = _get(env, f"/projects/{env['modern']}/modernization/target-architecture/versions/{bad}/packet").json()
    assert body["ok"] is False and body["problems"]


async def test_the_export_renders_that_version(env):
    v = await _draft(env)
    r = _get(env, f"/projects/{env['modern']}/modernization/target-architecture/versions/{v}/export?format=docx")
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"].endswith(f'target-architecture-v{v}.docx"')


async def test_the_interface_route_reads_the_pulled_code(env, tmp_path, monkeypatch):
    monkeypatch.setattr(legacy_code, "_root", lambda: tmp_path / "legacy-code")
    url = f"/projects/{env['modern']}/modernization/legacy-code/interfaces"
    assert _get(env, url).json()["status"] == "none"
    build_repo(legacy_code.checkout_dir(env["modern"]))
    legacy_code._write_record(env["modern"], {"status": "ready", "pull": {"url": "x", "commit": "c0ffee1",
                                                                         "name": "claimtrack", "profile": {"modules": []}}})
    async with get_db_session_for_tenant(env["org"]) as s:
        await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage="discovery",
                                     payload=stored_assessment(), produced_by="u-ba")
    body = _get(env, url).json()
    assert body["status"] == "ready" and body["inventory"]["total"] == 21
    assert any(i["module"] == "M-02" for i in body["inventory"]["items"])


@pytest.mark.parametrize("path", [
    "/projects/{p}/modernization/target-architecture",
    "/projects/{p}/modernization/target-architecture/versions/1/packet",
    "/projects/{p}/modernization/legacy-code/interfaces",
])
async def test_the_routes_are_guarded_by_track_membership_and_reach(env, path):
    await _draft(env)
    assert _get(env, path.format(p=env["green"])).status_code == 403          # not a Track 3 project
    assert _get(env, path.format(p=env["modern"]), user="u-stranger").status_code == 404  # not a member
    await grant_role("u-dev", env["modern"], "developer", tenant_id=env["org"], scope_kind="project")
    assert _get(env, path.format(p=env["modern"]), user="u-dev").status_code == 403       # no reach
    assert _get(env, path.format(p=env["modern"])).status_code == 200
