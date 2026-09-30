"""Migration Strategy on the real database (`sdlc_product_test`), through the real tools and app.

  record    inputs are the three versions THIS TURN pinned (brief, assessment, design, all read and
            recorded as consumed); no plan without all three; a refused plan freezes nothing; an
            accepted one is stored, frozen with its pins, placements, computed order/calendar/effort
  board     preview shows exactly what would be written, from the RECORDED plan; writing needs an
            Architect or Project Admin OF THIS PROJECT and this turn's consent; the items written are
            the previewed ones
  approval  (not the producer) places every planned module designed → sequenced with its wave and
            criteria, in the publish transaction; a module not on the ledger, a revised plan that
            re-waves a migrating module, and a plan without placements are refused and roll back; a
            revised plan updates modules still sequenced
  routes    latest, packet (hands over to Equivalence Testing), export, guarded like the rest
"""
from __future__ import annotations

import json
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from agents_orchestrator.modernization_common.standalone import _chat_run, upstream_from_pages
from agents_orchestrator.modernization_common.versions import reset_built_from
from agents_orchestrator.strategy_agent.tools import strategy_tools as tools
from config.auth.jwt import create_access_token
from config.connectors.context import clear_connector, set_connector
from config.ws_helper import (
    reset_session_id, set_consequential_approved, set_orchestrator_run, set_project_id, set_run_id,
    set_session_id, set_tenant_id, set_user_id,
)
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.models.artifacts import TargetDesignArtifact
from shared.models.orm import ModernizationModule
from shared.services import modernization_ledger as ledger
from shared.services.artifact_versions import publish_version, reject_version, snapshot_stage_payload
from tests.design_modernization.claimtrack import stored_assessment, stored_brief
from tests.strategy.scenarios import claimtrack

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "strategy"
APPROVE = [f"artifact:approve_{STAGE}", "artifact:view"]
PATHS = {m["id"]: m["path"] for m in stored_assessment()["modules"]}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


def _plan() -> dict:
    return claimtrack()[3]


def _stored_design() -> dict:
    return TargetDesignArtifact(**claimtrack()[2], system_name="ClaimTrack", module_paths=PATHS).model_dump(mode="json")


@pytest.fixture
async def env():
    org, bu, modern, green = (str(_uuid.uuid4()) for _ in range(4))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseF')"),
                        {"i": org, "s": f"pf-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        for pid, track in ((modern, "modernization"), (green, "greenfield")):
            await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                                 "VALUES (:i, :w, :t, 'ClaimTrack', :tr)"), {"i": pid, "w": bu, "t": org, "tr": track})
    for user, role in (("u-arch", "architect"), ("u-arch2", "architect"), ("u-pa", "project_admin"), ("u-ba", "ba")):
        await grant_role(user, modern, role, tenant_id=org, scope_kind="project")
    await grant_role("u-arch2", green, "architect", tenant_id=org, scope_kind="project")  # a member there
    return {"org": org, "modern": modern, "green": green}


async def _approved_inputs(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        for stage, payload, producer in (("requirements_modernization", stored_brief(), "u-ba"),
                                         ("discovery", stored_assessment(), "u-ba"),
                                         ("design_modernization", _stored_design(), "u-arch2")):
            ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage=stage,
                                               payload=payload, produced_by=producer)
            await publish_version(s, tenant_id=env["org"], project_id=env["modern"], stage=stage,
                                  version=ref.version, published_by="u-pa")
        await ledger.design_approved(s, tenant_id=env["org"], project_id=env["modern"], actor="u-arch2",
                                     artifact=ledger.ArtifactRef("target_design_artifacts", 1),
                                     modules=[{"module_id": m, "legacy_path": p, "patterns": DESIGNED[m]}
                                              for m, p in PATHS.items()])


DESIGNED = {m["module_id"]: m["patterns"] for m in claimtrack()[2]["modules"]}


@pytest.fixture
async def chat(env):
    set_tenant_id(env["org"])
    set_project_id(env["modern"])
    set_user_id("u-arch")
    set_orchestrator_run(False)
    set_consequential_approved(False)
    token = set_session_id(f"s-{env['modern'][:8]}")
    set_run_id(await _chat_run(env["org"], env["modern"], STAGE))
    tools._LAST_PLAN.clear()
    yield env
    reset_built_from()
    reset_session_id(token)
    clear_connector()
    set_consequential_approved(False)
    for fn in (set_tenant_id, set_project_id, set_run_id):
        fn(None)
    set_user_id("")


async def _turn(env):
    reset_built_from()
    return await upstream_from_pages(env["modern"], env["org"], STAGE, consumed_by="u-arch",
                                     consumer_session=f"s-{env['modern'][:8]}")


async def _versions(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text(
            "SELECT version, status, produced_by, built_from, payload FROM artifact_versions "
            "WHERE project_id = :p AND stage = :s ORDER BY version"), {"p": env["modern"], "s": STAGE})).mappings().all()


async def _record(plan=None):
    return await tools.record_migration_strategy.ainvoke({"plan": plan or _plan()})


# ── recording ────────────────────────────────────────────────────────────────

async def test_no_plan_without_all_three_inputs(chat):
    await _turn(chat)
    out = await _record()
    assert out.startswith("NOT RECORDED") and "no target design" in out and "no migration-intent brief" in out
    assert await _versions(chat) == []


async def test_the_upstream_reader_reads_and_records_all_three(chat):
    await _approved_inputs(chat)
    context = await _turn(chat)
    assert "Target design v1 (approved)" in context and "TRAPS (each needs a criterion)" in context
    async with get_db_session_for_tenant(chat["org"]) as s:
        stages = (await s.execute(text(
            "SELECT v.stage FROM artifact_consumptions c JOIN artifact_versions v ON v.id = c.version_id "
            "WHERE c.consumer_stage = 'strategy' ORDER BY v.stage"))).scalars().all()
    assert stages == ["design_modernization", "discovery", "requirements_modernization"]


async def test_an_accepted_plan_is_stored_frozen_pinned_and_returned(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    out = await _record()
    assert out.startswith("# Migration Strategy — ClaimTrack"), out[:300]
    assert "foundation plus 4 waves, 10 equivalence criteria" in out and "Recorded as migration plan v1 (draft)" in out
    [row] = await _versions(chat)
    assert (row["version"], row["status"], row["produced_by"]) == (1, "draft", "u-arch")
    assert sorted(p["stage"] for p in row["built_from"]) == ["design_modernization", "discovery", "requirements_modernization"]
    p = row["payload"]
    assert {x["module_id"]: x["wave"] for x in p["placements"]} == {
        "M-05": "W1", "M-01": "W2", "M-02": "W2", "M-03": "W3", "M-04": "W4"}
    assert [c["ref"] for c in p["calendar_checked"]] == ["baseline-late:EC-03"]
    assert p["proposed_order"]["order"][0]["modules"] == ["M-01"]
    assert p["effort_table"]["is_estimate"] is True and p["freeze_policy"]["from"] == "2027-02-01"
    async with get_db_session_for_tenant(chat["org"]) as s:
        column = (await s.execute(text("SELECT strategy_artifacts FROM runs WHERE project_id = :p AND "
                                       "strategy_artifacts IS NOT NULL"), {"p": chat["modern"]})).scalar_one()
    assert column["summary"] == p["summary"]


async def test_a_refused_plan_names_the_problems_and_freezes_nothing(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    plan = _plan()
    plan["calendar_conflicts"] = [c for c in plan["calendar_conflicts"] if c.get("ref") != "baseline-late:EC-03"]
    plan["equivalence_criteria"] = [c for c in plan["equivalence_criteria"] if c["id"] != "EC-10"]
    plan["baseline_plan"] = [b for b in plan["baseline_plan"] if b["ec_id"] != "EC-10"]
    plan["waves"][3]["exit_criteria"].remove("EC-10")
    out = await _record(plan)
    assert out.startswith("NOT RECORDED YET")
    assert "No criterion protects CT-04" in out and "baseline-late:EC-03" in out
    assert await _versions(chat) == []


async def test_the_orchestrator_plans_from_its_own_run_and_freezes_nothing(chat):
    run_id = str(_uuid.uuid4())
    async with get_db_session_for_tenant(chat["org"]) as s:
        await s.execute(text(
            "INSERT INTO runs (id, project_id, tenant_id, stage, status, trigger, migration_intent_payload, "
            "discovery_artifacts, target_design_artifacts) VALUES (:i, :p, :t, 'orchestrator', 'running', 'chat', "
            "CAST(:b AS jsonb), CAST(:a AS jsonb), CAST(:d AS jsonb))"),
            {"i": run_id, "p": chat["modern"], "t": chat["org"], "b": json.dumps(stored_brief()),
             "a": json.dumps(stored_assessment()), "d": json.dumps(_stored_design())})
    set_orchestrator_run(True)
    set_run_id(run_id)
    try:
        out = await _record()
        tools._LAST_PLAN.clear()  # a restart, or another worker: the plan is read back from the run
        preview = await tools.preview_wave_work_items.ainvoke({})
        versioned = await tools.preview_wave_work_items.ainvoke({"version": 2})
    finally:
        set_orchestrator_run(False)
    assert "Recorded in this Orchestrator conversation" in out and await _versions(chat) == []
    assert preview.startswith("From the plan recorded in this conversation"), preview
    assert "Plan versions exist on the Migration Strategy page" in versioned


async def test_an_incomplete_draft_is_explained_not_crashed_on(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    out = await tools.check_calendar.ainvoke({"plan": {"waves": [{"modules": ["M-01"], "ends": "2028-01-01"}]}})
    assert out.startswith("The draft could not be checked (KeyError") and "Every wave needs an id" in out
    out = await tools.estimate_effort.ainvoke({"waves": [{"modules": ["M-01"]}]})
    assert out.startswith("The waves could not be read"), out


# ── the board ────────────────────────────────────────────────────────────────

class _Board:
    display_name = "Azure DevOps"
    access_level = "read_write"

    def __init__(self):
        self.created: list[dict] = []

    async def read_adapter(self, op, **kw):
        return [{"name": "ClaimTrack"}]

    async def write_adapter(self, op, **kw):
        self.created.append(kw)
        return {"work_item_id": str(len(self.created))}


async def test_the_preview_is_built_from_the_recorded_plan(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    assert "No migration plan" in await tools.preview_wave_work_items.ainvoke({})
    await _record()
    out = await tools.preview_wave_work_items.ainvoke({"item_type": "Product Backlog Item"})
    assert out.startswith("From migration plan v1 (draft), the board would get 4 Feature(s) and 5 Product Backlog Item(s)")
    assert "Feature: **W3 — Settlement batch**" in out
    assert "Product Backlog Item: Migrate M-03 (in_place_upgrade+parallel_run) — Done when: EC-02 bank payment file" in out


async def test_writing_needs_consent_on_this_turn(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    await _record()
    board = _Board()
    set_connector(board)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert "NOT DONE" in out and board.created == []


async def test_writing_needs_an_architect_or_project_admin_of_this_project(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    await _record()
    set_user_id("u-ba")  # a BA of this project, even with consent, does not write the plan
    set_consequential_approved(True)
    board = _Board()
    set_connector(board)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert board.created == [] and ("Architect" in out or "NOT DONE" in out), out


async def test_an_architect_of_another_project_does_not_write_this_plan(chat):
    """Permissions are a tenant-wide union: an Architect of ANOTHER project passes the Consequential
    check with consent. Only the role check on THIS project stops them."""
    await _approved_inputs(chat)
    await _turn(chat)
    await _record()
    await grant_role("u-elsewhere", chat["green"], "architect", tenant_id=chat["org"], scope_kind="project")
    set_user_id("u-elsewhere")
    set_consequential_approved(True)
    board = _Board()
    set_connector(board)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert out.startswith("Only an Architect or a Project Admin of this project"), out
    assert board.created == []


async def test_a_read_only_board_is_refused(chat):
    board = _Board()
    board.access_level = "read"
    set_connector(board)
    set_consequential_approved(True)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert "cannot be used to write" in out and board.created == []


async def test_a_rejected_plan_is_not_written_to_the_board(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    await _record()
    async with get_db_session_for_tenant(chat["org"]) as s:
        await reject_version(s, tenant_id=chat["org"], project_id=chat["modern"], stage=STAGE, version=1,
                             rejected_by="u-arch2", reason="waves too long")
    board = _Board()
    set_connector(board)
    set_consequential_approved(True)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert "Not written: migration plan v1 (rejected) was rejected" in out and board.created == [], out


async def test_the_owner_with_consent_writes_exactly_the_preview(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    await _record()
    board = _Board()
    set_connector(board)
    set_consequential_approved(True)
    out = await tools.create_wave_work_items.ainvoke({"project": "ClaimTrack"})
    assert "Created Feature #1: W1 — Reports" in out, out
    titles = [c["title"] for c in board.created]
    assert titles[:2] == ["W1 — Reports", "Migrate M-05 (in_place_upgrade+parallel_run)"]
    assert len(board.created) == 9 and {c["project"] for c in board.created} == {"ClaimTrack"}
    children = [c for c in board.created if c["parent_id"]]
    assert len(children) == 5 and children[0]["parent_id"] == "1"


# ── approval → ledger ────────────────────────────────────────────────────────

def _client(env, user, perms=APPROVE):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=perms)}


def _publish(env, v, user, body=None):
    client, hdr = _client(env, user)
    return client.post(f"/artifact-versions/{env['modern']}/stages/{STAGE}/versions/{v}/publish",
                       json=body or {}, headers=hdr)


async def _recorded_version(env, payload_edit=None):
    """A plan version as the record tool stores it (built through the tool)."""
    set_tenant_id(env["org"])
    set_project_id(env["modern"])
    set_user_id("u-arch")
    set_orchestrator_run(False)
    token = set_session_id(f"s-{_uuid.uuid4()}")
    set_run_id(await _chat_run(env["org"], env["modern"], STAGE))
    try:
        await _turn(env)
        out = await _record()
        assert "Recorded as migration plan" in out, out[:500]
    finally:
        reset_built_from()
        reset_session_id(token)
    rows = await _versions(env)
    if payload_edit:
        payload = payload_edit(dict(rows[-1]["payload"]))
        async with get_db_session_for_tenant(env["org"]) as s:
            return (await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage=STAGE,
                                                 payload=payload, produced_by="u-arch")).version
    return rows[-1]["version"]


async def _ledger(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return {r.module_id: r for r in await ledger.list_modules(s, env["modern"])}


async def _status(env, v):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text("SELECT status FROM artifact_versions WHERE project_id = :p AND stage = :s "
                                     "AND version = :v"), {"p": env["modern"], "s": STAGE, "v": v})).scalar_one()


async def test_approval_sequences_every_planned_module(env):
    await _approved_inputs(env)
    v = await _recorded_version(env)
    assert {r.state for r in (await _ledger(env)).values()} == {"designed"}, "recording writes nothing to the ledger"
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 200, r.text
    rows = await _ledger(env)
    assert {m: (x.state, x.wave) for m, x in rows.items()} == {
        "M-01": ("sequenced", "W2"), "M-02": ("sequenced", "W2"), "M-03": ("sequenced", "W3"),
        "M-04": ("sequenced", "W4"), "M-05": ("sequenced", "W1")}
    assert rows["M-03"].ec_ids == ["EC-02", "EC-09", "EC-10", "EC-08"]
    assert rows["M-03"].history[-1]["artifact"] == {"stage": "strategy_artifacts", "version": v}


async def test_the_producer_cannot_approve(env):
    await _approved_inputs(env)
    v = await _recorded_version(env)
    assert _publish(env, v, "u-arch").status_code == 403
    assert await _status(env, v) == "draft" and {r.state for r in (await _ledger(env)).values()} == {"designed"}


async def test_a_project_admin_approves_as_fallback(env):
    await _approved_inputs(env)
    v = await _recorded_version(env)
    r = _publish(env, v, "u-pa", {"fallbackReason": "Architects on leave"})
    assert r.status_code == 200 and r.json()["approvedAs"] == "fallback:project_admin", r.text


async def test_a_module_not_on_the_ledger_refuses_and_rolls_back(env):
    await _approved_inputs(env)
    v = await _recorded_version(env)
    async with get_db_session_superuser() as s:  # simulate a design never approved for M-04
        await s.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": env["org"]})
        await s.execute(text("DELETE FROM modernization_modules WHERE project_id = CAST(:p AS uuid) AND module_id = 'M-04'"),
                        {"p": env["modern"]})
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409 and "M-04 is not on the ledger" in r.json()["detail"], r.text
    assert await _status(env, v) == "draft"
    assert {x.state for x in (await _ledger(env)).values()} == {"designed"}


async def test_a_revised_plan_updates_sequenced_modules_and_refuses_to_rewave_a_migrating_one(env):
    await _approved_inputs(env)
    assert _publish(env, await _recorded_version(env), "u-arch2").status_code == 200
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.baseline_accepted(s, project_id=env["modern"], module_id="M-05", baseline_ids=["BL-04"],
                                       actor="u-qa", artifact=ledger.ArtifactRef("equivalence_artifacts", 1))
    def rewave(p):
        for x in p["placements"]:
            if x["module_id"] in ("M-05", "M-04"):
                x["wave"] = "W9"
        return p
    v2 = await _recorded_version(env, rewave)
    r = _publish(env, v2, "u-arch2")
    assert r.status_code == 409 and "M-05 is already baselined in W1; this plan moves it to W9" in r.json()["detail"]
    assert (await _ledger(env))["M-04"].wave == "W4"  # rolled back, nothing half-applied
    def only_m04(p):
        for x in p["placements"]:
            if x["module_id"] == "M-04":
                x["wave"] = "W5"
        return p
    v3 = await _recorded_version(env, only_m04)
    assert _publish(env, v3, "u-arch2").status_code == 200
    m04 = (await _ledger(env))["M-04"]
    assert (m04.state, m04.wave, m04.history[-1]["note"]) == ("sequenced", "W5", "plan revised")


async def test_a_plan_of_another_design_version_is_not_approved(env):
    """The ledger holds the APPROVED design's patterns: a plan built on a draft design (or one a newer
    approved design has overtaken) differs from them, and is refused (review fix #4)."""
    await _approved_inputs(env)
    async with get_db_session_for_tenant(env["org"]) as s:  # the approved design now keeps M-04
        row = (await s.execute(select(ModernizationModule).where(
            ModernizationModule.project_id == env["modern"], ModernizationModule.module_id == "M-04"))).scalar_one()
        row.patterns = ["keep"]
    v = await _recorded_version(env)
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409 and "M-04 is keep in the approved target design but" in r.json()["detail"], r.text
    assert await _status(env, v) == "draft"
    assert {x.state for x in (await _ledger(env)).values()} == {"designed"}


async def test_a_plan_that_leaves_out_a_module_the_design_moves_is_not_approved(env):
    await _approved_inputs(env)
    v = await _recorded_version(env, lambda p: {**p, "placements": [x for x in p["placements"]
                                                                    if x["module_id"] != "M-02"]})
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409 and "moves M-02 (in_place_upgrade+strangler_fig), which this plan does not place"         in r.json()["detail"], r.text
    assert await _status(env, v) == "draft"


async def test_a_revision_keeps_the_criteria_of_a_module_past_planning(env):
    await _approved_inputs(env)
    assert _publish(env, await _recorded_version(env), "u-arch2").status_code == 200
    async with get_db_session_for_tenant(env["org"]) as s:
        await ledger.baseline_accepted(s, project_id=env["modern"], module_id="M-05", baseline_ids=["BL-04"],
                                       actor="u-qa", artifact=ledger.ArtifactRef("equivalence_artifacts", 1))
    def renumber(p):
        for x in p["placements"]:
            if x["module_id"] == "M-05":
                x["ec_ids"] = ["EC-99"]
        return p
    r = _publish(env, await _recorded_version(env, renumber), "u-arch2")
    assert r.status_code == 409 and "M-05 is already baselined with criteria EC-03, EC-06, EC-08"         in r.json()["detail"], r.text
    assert (await _ledger(env))["M-05"].ec_ids == ["EC-03", "EC-06", "EC-08"]


async def test_a_plan_without_placements_is_not_approved(env):
    await _approved_inputs(env)
    v = await _recorded_version(env, lambda p: {**p, "placements": []})
    r = _publish(env, v, "u-arch2")
    assert r.status_code == 409 and "Record the plan with the Migration Strategy agent" in r.json()["detail"]


# ── routes ───────────────────────────────────────────────────────────────────

def _get(env, path, user="u-arch2", perms=("artifact:view",)):
    client, hdr = _client(env, user, list(perms))
    return client.get(path, headers=hdr)


async def test_the_packet_export_and_latest_routes(env):
    await _approved_inputs(env)
    v = await _recorded_version(env)
    body = _get(env, f"/projects/{env['modern']}/modernization/strategy/versions/{v}/packet").json()
    assert body["ok"] is True and body["packet"]["agent_id"] == "strategy"
    assert "placements" not in body["packet"]["payload"] and body["packet"]["payload"]["freeze_policy"]["from"] == "2027-02-01"
    r = _get(env, f"/projects/{env['modern']}/modernization/strategy/versions/{v}/export?format=docx")
    assert r.status_code == 200 and r.headers["content-disposition"].endswith(f'migration-strategy-v{v}.docx"')
    latest = _get(env, f"/projects/{env['modern']}/modernization/strategy").json()
    assert latest["payload"]["summary"].startswith("Foundation plus four waves")


@pytest.mark.parametrize("path", ["/projects/{p}/modernization/strategy",
                                  "/projects/{p}/modernization/strategy/versions/1/packet"])
async def test_the_routes_are_guarded(env, path):
    await _approved_inputs(env)
    await _recorded_version(env)
    assert _get(env, path.format(p=env["green"])).status_code == 403
    assert _get(env, path.format(p=env["modern"]), user="u-stranger").status_code == 404
    assert _get(env, path.format(p=env["modern"]), user="u-ba").status_code == 403
    assert _get(env, path.format(p=env["modern"])).status_code == 200
