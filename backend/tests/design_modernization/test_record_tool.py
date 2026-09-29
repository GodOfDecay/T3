"""`record_target_design` and the read tools, on the real database (`sdlc_product_test`).

Guarding: the inputs are the versions THIS TURN pinned, read through the platform's own reader
(`upstream_from_pages` → consumptions recorded, `built_from` pinned); nothing is recorded without
both a brief and an assessment; a refused design freezes nothing; an accepted one is stored on the
run, frozen as the next version with its pins and the module paths, and returned as the document;
an Orchestrator conversation designs from its own run and freezes nothing.
"""
from __future__ import annotations

import json
import uuid as _uuid

import pytest
from sqlalchemy import text

from agents_orchestrator.design_modernization_agent.tools import design_tools as tools
from agents_orchestrator.modernization_common import legacy_code
from agents_orchestrator.modernization_common.standalone import _chat_run, upstream_from_pages
from agents_orchestrator.modernization_common.versions import reset_built_from
from config.ws_helper import (
    reset_session_id, set_orchestrator_run, set_project_id, set_run_id, set_session_id, set_tenant_id,
    set_user_id,
)
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services.artifact_versions import publish_version, snapshot_stage_payload
from tests.design_modernization.claimtrack import build_repo, design_payload, stored_assessment, stored_brief

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "design_modernization"


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def env(tmp_path, monkeypatch):
    org, bu, project = (str(_uuid.uuid4()) for _ in range(3))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseE')"),
                        {"i": org, "s": f"pe-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', 'modernization')"), {"i": project, "w": bu, "t": org})
    monkeypatch.setattr(legacy_code, "_root", lambda: tmp_path / "legacy-code")
    tools._INVENTORY.clear()
    tools._LAST_DESIGN.clear()
    set_tenant_id(org)
    set_project_id(project)
    set_user_id("u-arch")
    set_orchestrator_run(False)
    token = set_session_id(f"s-{project[:8]}")
    set_run_id(await _chat_run(org, project, STAGE))
    yield {"org": org, "project": project}
    reset_built_from()
    reset_session_id(token)
    set_tenant_id(None)
    set_project_id(None)
    set_user_id("")
    set_run_id(None)


async def _approved_inputs(env, brief=None, assessment=None):
    async with get_db_session_for_tenant(env["org"]) as s:
        for stage, payload in (("requirements_modernization", brief or stored_brief()),
                               ("discovery", assessment or stored_assessment())):
            ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["project"], stage=stage,
                                               payload=payload, produced_by="u-ba")
            await publish_version(s, tenant_id=env["org"], project_id=env["project"], stage=stage,
                                  version=ref.version, published_by="u-ba2")


def _pull(env, commit="a1b2c3d"):
    root = legacy_code.checkout_dir(env["project"])
    build_repo(root)
    legacy_code._write_record(env["project"], {"status": "ready", "pull": {
        "url": "https://dev.azure.com/o/p/_git/claimtrack", "commit": commit, "name": "claimtrack",
        "provider": "ado", "branch": "main", "profile": {"modules": []}}})


async def _turn(env):
    """What the page socket does before the graph runs: read (and pin) the upstream work."""
    reset_built_from()
    return await upstream_from_pages(env["project"], env["org"], STAGE, consumed_by="u-arch",
                                     consumer_session=f"s-{env['project'][:8]}")


async def _versions(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text(
            "SELECT version, status, produced_by, built_from, payload FROM artifact_versions "
            "WHERE project_id = :p AND stage = :s ORDER BY version"), {"p": env["project"], "s": STAGE})).mappings().all()


async def _record(design):
    return await tools.record_target_design.ainvoke({"design": design})


async def test_nothing_is_recorded_without_a_brief_and_an_assessment(env):
    _pull(env)
    await _turn(env)
    out = await _record(design_payload())
    assert out.startswith("NOT RECORDED")
    assert "no migration-intent brief" in out and "no Dependency and Risk assessment" in out
    assert await _versions(env) == []


async def test_the_upstream_reader_gives_both_inputs_and_records_the_reads(env):
    await _approved_inputs(env)
    context = await _turn(env)
    assert "Migration-intent brief v1 (approved)" in context
    assert "Dependency and Risk assessment v1 (approved)" in context
    assert "MUST NOT CHANGE (the user's own words): “/api/v1 claims API our broker partners call”" in context
    assert "M-03 claimtrack-batch (claimtrack-batch): llm_assisted, score 49" in context
    async with get_db_session_for_tenant(env["org"]) as s:
        reads = (await s.execute(text(
            "SELECT v.stage FROM artifact_consumptions c JOIN artifact_versions v ON v.id = c.version_id "
            "WHERE c.consumer_stage = :c ORDER BY v.stage"), {"c": STAGE})).scalars().all()
    assert reads == ["discovery", "requirements_modernization"]


async def test_an_accepted_design_is_stored_frozen_pinned_and_returned_as_the_document(env):
    await _approved_inputs(env)
    _pull(env)
    await _turn(env)
    out = await _record(design_payload())
    assert out.startswith("# Target Architecture — ClaimTrack"), out[:400]
    assert "Built from migration-intent brief v1 (approved) and assessment v1 (approved, commit `a1b2c3d`)" in out
    assert "Recorded as target design v1 (draft)" in out
    assert "5 modules:" in out and "4 frozen contracts; 7 traps; 8 ADRs" in out
    [row] = await _versions(env)
    assert (row["version"], row["status"], row["produced_by"]) == (1, "draft", "u-arch")
    assert sorted((p["stage"], p["version"], p["status"]) for p in row["built_from"]) == [
        ("discovery", 1, "published"), ("requirements_modernization", 1, "published")]
    payload = row["payload"]
    assert payload["module_paths"]["M-03"] == "claimtrack-batch"
    assert payload["sources"]["assessment"] == {"version": 1, "status": "published", "commit": "a1b2c3d",
                                                "repository": stored_assessment()["repository"]["url"]}
    assert payload["interfaces"]["total"] == 21 and payload["system_name"] == "ClaimTrack"
    assert payload["frozen_contracts"][0]["brief_item"] == "/api/v1 claims API our broker partners call"
    async with get_db_session_for_tenant(env["org"]) as s:
        column = (await s.execute(text("SELECT target_design_artifacts FROM runs WHERE project_id = :p "
                                       "AND target_design_artifacts IS NOT NULL"), {"p": env["project"]})).scalar_one()
    assert column["summary"] == payload["summary"]


async def test_a_refused_design_names_the_problem_and_freezes_nothing(env):
    await _approved_inputs(env)
    _pull(env)
    await _turn(env)
    d = design_payload()
    d["modules"][2]["module"] = "claimtrack-reports"
    d["adrs"][0]["options"] = ["only one"]
    out = await _record(d)
    assert out.startswith("NOT RECORDED YET") and "adrs.0.options" in out, out
    d["adrs"][0]["options"] = ["a", "b"]
    out = await _record(d)
    assert "M-03 is claimtrack-batch in assessment v1" in out
    assert await _versions(env) == []


async def test_a_draft_input_makes_the_design_provisional_and_says_so(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        for stage, payload in (("requirements_modernization", stored_brief()), ("discovery", stored_assessment())):
            await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["project"], stage=stage,
                                         payload=payload, produced_by="u-ba")
    _pull(env)
    await _turn(env)
    out = await _record(design_payload())
    assert "brief v1 (not yet approved)" in out
    assert "Built from assessment v1 (not yet approved): the design is provisional until it is approved." in out
    [row] = await _versions(env)
    assert {p["status"] for p in row["built_from"]} == {"draft"}


async def test_code_at_another_commit_is_refused(env):
    """Review fix #12: locations checked against other code prove nothing about the assessed modules."""
    await _approved_inputs(env)
    _pull(env, commit="ffff999")
    await _turn(env)
    out = await _record(design_payload())
    assert out.startswith("NOT RECORDED YET")
    assert "pulled code is at commit ffff999" in out and "made at a1b2c3d" in out
    assert await _versions(env) == []


async def test_the_inventory_is_attributed_with_the_modules_asked_for(env, tmp_path):
    """Review fix #5: a scan attributed with names is not served later to a caller with ids."""
    root = build_repo(tmp_path / "repo")
    by_name = tools.inventory_for(root, "c1", [{"name": "claimtrack-web", "path": "claimtrack-web"}])
    by_id = tools.inventory_for(root, "c1", [{"id": "M-02", "name": "claimtrack-web", "path": "claimtrack-web"}])
    assert {i["module"] for i in by_name["items"]} >= {"claimtrack-web"}
    assert "M-02" in {i["module"] for i in by_id["items"]}
    assert "claimtrack-web" not in {i["module"] for i in by_id["items"]}


async def test_export_follows_the_pages_newest_version_after_a_restore(env):
    """Review fix #11: after a restore in this chat, export reads what the page shows."""
    await _approved_inputs(env)
    _pull(env)
    await _turn(env)
    assert "Recorded as target design v1" in await _record(design_payload())
    async with get_db_session_for_tenant(env["org"]) as s:
        [row] = await _versions(env)
        await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["project"], stage=STAGE,
                                     payload={**row["payload"], "summary": "the restored one"}, produced_by="u-arch")
    assert (await tools._latest_design())["summary"] == "the restored one"


async def test_the_orchestrator_designs_from_its_own_run_and_freezes_nothing(env):
    run_id = str(_uuid.uuid4())
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text(
            "INSERT INTO runs (id, project_id, tenant_id, stage, status, trigger, migration_intent_payload, "
            "discovery_artifacts) VALUES (:i, :p, :t, 'orchestrator', 'running', 'chat', "
            "CAST(:b AS jsonb), CAST(:a AS jsonb))"),
            {"i": run_id, "p": env["project"], "t": env["org"], "b": json.dumps(stored_brief()),
             "a": json.dumps(stored_assessment())})
    set_orchestrator_run(True)
    set_run_id(run_id)
    legacy_code.checkout_dir(env["project"], run_id).parent.mkdir(parents=True, exist_ok=True)
    root = legacy_code.checkout_dir(env["project"], run_id)
    build_repo(root)
    legacy_code._write_record(env["project"], {"status": "ready", "pull": {"url": "x", "commit": "a1b2c3d"}}, run_id)
    try:
        out = await _record(design_payload())
    finally:
        set_orchestrator_run(False)
    assert out.startswith("# Target Architecture"), out[:300]
    assert "Recorded in this Orchestrator conversation" in out
    assert await _versions(env) == []


async def test_the_read_tools_show_the_pinned_inputs(env):
    await _approved_inputs(env)
    _pull(env)
    await _turn(env)
    brief = await tools.read_migration_brief.ainvoke({})
    assert "brief v1 (approved)" in brief and "“bank payment file format”" in brief
    assessment = await tools.read_assessment.ainvoke({})
    assert "| M-03 | claimtrack-batch | `claimtrack-batch` | llm_assisted | 49 |" in assessment
    assert "Not assessable statically" in assessment and "scheduler configuration held outside" in assessment
    detail = await tools.get_module_detail.ainvoke({"module": "m-02"})
    assert json.loads(detail)["name"] == "claimtrack-web"
    captured = await tools.capture_legacy_interfaces.ainvoke({})
    assert "GET /api/v1/claims/{id}" in captured and "pulled code is at commit" not in captured


async def test_export_says_when_nothing_is_recorded(env):
    await _turn(env)
    assert "No target design has been recorded yet" in await tools.export_target_design.ainvoke({})
