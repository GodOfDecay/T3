"""Equivalence Testing, Baseline mode — through the real tools, database and sandbox (Phase G).

The chain for ClaimTrack Lite: an approved target design and migration plan put M-01 and M-02 on the
ledger as `sequenced`; the legacy code is pulled through the ordinary `pull_now`; the agent plans a
capture, captures (Consequential: QA or Project Admin of THIS project, and their yes this turn),
records the baseline with its rule proposals, and a second QA accepts it — the ledger moves both
modules to `baselined`. Around it, every refusal: no approved plan, an Orchestrator conversation,
the wrong role, no consent, a module not sequenced, a missing or invented proposal, a plan revised
since the capture, a failed capture (nothing kept), and an acceptance the ledger refuses.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agents_orchestrator.modernization_common import legacy_code
from agents_orchestrator.modernization_common.standalone import _chat_run, upstream_from_pages
from agents_orchestrator.modernization_common.versions import reset_built_from
from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore
from agents_orchestrator.testing_modernization_agent.tools import equivalence_tools as tools
from config.auth.jwt import create_access_token
from config.ws_helper import (
    reset_session_id, set_consequential_approved, set_orchestrator_run, set_project_id, set_run_id,
    set_session_id, set_tenant_id, set_user_id,
)
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.models.artifacts import TargetDesignArtifact
from shared.services import modernization_ledger as ledger
from shared.services.artifact_versions import publish_version, snapshot_stage_payload
from tests.design_modernization.claimtrack import fixture
from tests.testing_modernization import lite

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "testing_modernization"
APPROVE = [f"artifact:approve_{STAGE}", "artifact:view"]


def _docker_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_docker = pytest.mark.skipif(not _docker_up(), reason="Docker is not running")


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


def _design() -> dict:
    return TargetDesignArtifact(**fixture("design")["payload"], system_name="ClaimTrack Lite",
                                module_paths={"M-01": "claims-api", "M-02": "settlement-batch"}).model_dump(mode="json")


@pytest.fixture
async def env(tmp_path):
    org, bu, modern = (str(_uuid.uuid4()) for _ in range(3))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseG')"),
                        {"i": org, "s": f"pg-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack Lite', 'modernization')"), {"i": modern, "w": bu, "t": org})
    for user, role in (("u-qa", "qa"), ("u-qa2", "qa"), ("u-pa", "project_admin"), ("u-arch", "architect"),
                       ("u-dev", "developer")):
        await grant_role(user, modern, role, tenant_id=org, scope_kind="project")
    # The legacy code, pulled the ordinary way from a local repository.
    repo = tmp_path / "claimtrack-lite"
    shutil.copytree(lite.SAMPLE, repo)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "sample"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True)
    record = await legacy_code.pull_now(modern, repo.resolve().as_uri(), "main", user_id="u-qa")
    assert record["status"] == "ready", record
    yield {"org": org, "modern": modern}
    shutil.rmtree(legacy_code.project_dir(modern), ignore_errors=True)
    shutil.rmtree(LocalBaselineStore().project_dir(modern), ignore_errors=True)


async def _approved_inputs(env, *, plan_approved=True):
    async with get_db_session_for_tenant(env["org"]) as s:
        for stage, payload, publish in (("design_modernization", _design(), True),
                                        ("strategy", lite.stored_plan(), plan_approved)):
            ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage=stage,
                                               payload=payload, produced_by="u-arch")
            if publish:
                await publish_version(s, tenant_id=env["org"], project_id=env["modern"], stage=stage,
                                      version=ref.version, published_by="u-pa")
        await ledger.design_approved(
            s, tenant_id=env["org"], project_id=env["modern"], actor="u-pa",
            artifact=ledger.ArtifactRef("target_design_artifacts", 1),
            modules=[{"module_id": m, "module_name": p, "legacy_path": p, "patterns": lite.DESIGNED[m]}
                     for m, p in (("M-01", "claims-api"), ("M-02", "settlement-batch"))])
        if plan_approved:
            await ledger.strategy_approved(
                s, project_id=env["modern"], actor="u-pa", artifact=ledger.ArtifactRef("strategy_artifacts", 1),
                placements=[{"module_id": "M-01", "wave": "W1", "patterns": lite.DESIGNED["M-01"],
                             "ec_ids": ["EC-01", "EC-02", "EC-04"]},
                            {"module_id": "M-02", "wave": "W2", "patterns": lite.DESIGNED["M-02"], "ec_ids": ["EC-03"]}])


@pytest.fixture
async def chat(env):
    set_tenant_id(env["org"])
    set_project_id(env["modern"])
    set_user_id("u-qa")
    set_orchestrator_run(False)
    set_consequential_approved(False)
    token = set_session_id(f"s-{env['modern'][:8]}")
    set_run_id(await _chat_run(env["org"], env["modern"], STAGE))
    yield env
    reset_built_from()
    reset_session_id(token)
    set_consequential_approved(False)
    for fn in (set_tenant_id, set_project_id, set_run_id):
        fn(None)
    set_user_id("")


async def _turn(env, user="u-qa"):
    reset_built_from()
    return await upstream_from_pages(env["modern"], env["org"], STAGE, consumed_by=user,
                                     consumer_session=f"s-{env['modern'][:8]}")


async def _capture():
    return await tools.capture_baseline.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})


async def _ledger(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return {r.module_id: r for r in await ledger.list_modules(s, env["modern"])}


async def _versions(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text(
            "SELECT version, status, produced_by, built_from, payload FROM artifact_versions "
            "WHERE project_id = :p AND stage = :s ORDER BY version"), {"p": env["modern"], "s": STAGE})).mappings().all()


def _client(env, user, perms=APPROVE):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=perms)}


def _publish(env, v, user, body=None):
    client, hdr = _client(env, user)
    return client.post(f"/artifact-versions/{env['modern']}/stages/{STAGE}/versions/{v}/publish",
                       json=body or {}, headers=hdr)


# ── reading and planning ────────────────────────────────────────────────────

async def test_the_profile_and_plan_are_read_and_a_capture_plan_is_shown_before_anything_runs(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    profile = await tools.get_capture_profile.ainvoke({})
    assert "sdlc-sandbox.json in the legacy code" in profile and "| settle | http | 6 |" in profile
    assert "EC-02" in await tools.read_migration_plan.ainvoke({})
    ledger_text = await tools.get_ledger.ainvoke({})
    assert "| M-01 claims-api | sequenced | W1 |" in ledger_text
    shown = await tools.plan_capture.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    assert "Runs the legacy system **twice**" in shown and "| EC-02 | settle | 6 |" in shown
    assert "EC-04 (a load test" in shown and "fraudscore" in shown
    assert LocalBaselineStore().list_captures(chat["modern"]) == []


async def test_no_capture_without_an_approved_plan(chat):
    await _approved_inputs(chat, plan_approved=False)
    await _turn(chat)
    out = await tools.plan_capture.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    assert "APPROVED plan" in out or "not yet approved" in out, out


async def test_an_orchestrator_conversation_does_not_capture(chat):
    await _approved_inputs(chat)
    set_orchestrator_run(True)
    try:
        out = await tools.capture_baseline.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    finally:
        set_orchestrator_run(False)
    assert "captured on the Equivalence Testing page" in out


async def test_a_module_not_yet_sequenced_is_not_baselined(chat):
    await _approved_inputs(chat)
    async with get_db_session_for_tenant(chat["org"]) as s:
        await ledger.block(s, project_id=chat["modern"], module_id="M-02", agent="testing_modernization",
                           reason="no sandbox image", actor="u-qa")
    await _turn(chat)
    out = await tools.plan_capture.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    assert "M-02 is blocked" in out and "before its migration starts" in out, out


async def test_a_capture_needs_qa_or_a_project_admin_of_this_project_and_their_yes(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    out = await _capture()
    assert "NOT DONE" in out or "confirm" in out.lower(), out
    set_user_id("u-dev")
    set_consequential_approved(True)
    out = await _capture()
    assert out.startswith("Only QA or a Project Admin of this project captures a baseline"), out
    assert LocalBaselineStore().list_captures(chat["modern"]) == []


# ── the whole chain, for real ───────────────────────────────────────────────

@needs_docker
async def test_capture_record_and_accept_move_the_modules_to_baselined(chat):
    await _approved_inputs(chat)
    await _turn(chat)
    set_consequential_approved(True)
    out = await _capture()
    assert "— complete" in out, out
    capture_id = re.search(r"cap-\d{14}-[0-9a-f]{6}", out).group(0)
    assert "| settle | 6 | requestId (6; <uuid> vs <uuid>), settledAt (4; <timestamp> vs <timestamp>) |" in out
    assert "- EC-01: requestId" in out and "- EC-02: requestId" in out
    # The model saw shapes only: no claimant, amount, id or time from the recordings.
    for leak in ("Test Claimant", "Zoë", "0.13", "960.0", "CLM-000"):
        assert leak not in out, leak
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", out)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", out)

    missing = await tools.record_baseline.ainvoke({"capture_id": capture_id, "rule_proposals": lite.PROPOSALS[:1]})
    assert missing.startswith("NOT RECORDED YET") and "for EC-02" in missing
    invented = await tools.record_baseline.ainvoke(
        {"capture_id": capture_id, "rule_proposals": [*lite.PROPOSALS, {"ec_id": "EC-01", "field": "claim.payout",
                                                                        "rule": "round to even"}]})
    assert "for a field that did not vary" in invented
    assert await _versions(chat) == []

    done = await tools.record_baseline.ainvoke({"capture_id": capture_id, "rule_proposals": lite.PROPOSALS})
    assert "# Baseline — ClaimTrack Lite" in done and "Recorded as baseline v1" in done, done[-400:]
    rows = await _versions(chat)
    payload = rows[0]["payload"]
    assert [(b["id"], b["module_id"], b["ec_ids"], b["count"]) for b in payload["baselines"]] == [
        ("BL-01", "M-01", ["EC-01"], 5), ("BL-02", "M-01", ["EC-02"], 6), ("BL-03", "M-02", ["EC-03"], 1)]
    assert {b["region"] for b in payload["baselines"]} == {"local-dev"}
    assert payload["placements"] == [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-02"]},
                                     {"module_id": "M-02", "baseline_ids": ["BL-03"]}]
    assert {p["artifact"] for p in rows[0]["built_from"]} >= {"strategy_artifacts", "target_design_artifacts"}
    text_payload = json.dumps(payload)
    assert "Test Claimant" not in text_payload and "0.13" not in text_payload
    assert LocalBaselineStore().read_manifest(chat["modern"], capture_id)["keep"] is True
    assert {r.state for r in (await _ledger(chat)).values()} == {"sequenced"}, "recording writes nothing to the ledger"

    assert _publish(chat, 1, "u-qa").status_code == 403, "the producer cannot accept it"
    r = _publish(chat, 1, "u-qa2")
    assert r.status_code == 200, r.text
    rows = await _ledger(chat)
    assert {m: (x.state, x.baseline_ids) for m, x in rows.items()} == {
        "M-01": ("baselined", ["BL-01", "BL-02"]), "M-02": ("baselined", ["BL-03"])}
    assert rows["M-01"].history[-1]["artifact"] == {"stage": "equivalence_artifacts", "version": 1}

    # The page routes: latest, captures (no recording), the packet and the export.
    client, hdr = _client(chat, "u-qa2")
    captures = client.get(f"/projects/{chat['modern']}/modernization/equivalence-testing/captures", headers=hdr).json()
    assert captures["captures"][0]["status"] == "complete" and "Test Claimant" not in json.dumps(captures)
    packet = client.get(f"/projects/{chat['modern']}/modernization/equivalence-testing/versions/1/packet", headers=hdr)
    assert packet.json()["ok"] is True and "capture" not in packet.json()["packet"]["payload"]
    export = client.get(f"/projects/{chat['modern']}/modernization/equivalence-testing/versions/1/export?format=docx",
                        headers=hdr)
    assert export.status_code == 200 and export.headers["content-disposition"].endswith('equivalence-baseline-v1.docx"')


@needs_docker
async def test_a_failed_capture_records_nothing_and_says_so(chat, monkeypatch):
    monkeypatch.setenv("SDLC_SANDBOX_HEALTH_SECONDS", "6")
    await _approved_inputs(chat)
    broken = json.loads((legacy_code.checkout_dir(chat["modern"]) / "sdlc-sandbox.json").read_text(encoding="utf-8"))
    broken["service"]["command"] = "python -c 'import sys; sys.exit(3)'"
    await _turn(chat)
    assert (await tools.save_capture_profile.ainvoke({"profile": broken})).startswith("Saved for this project")
    set_consequential_approved(True)
    out = await _capture()
    assert "FAILED" in out and "Nothing was recorded and no baseline was accepted" in out, out
    capture_id = re.search(r"cap-\d{14}-[0-9a-f]{6}", out).group(0)
    manifest = LocalBaselineStore().read_manifest(chat["modern"], capture_id)
    assert manifest["status"] == "failed" and "did not answer on /health" in manifest["error"]
    d = LocalBaselineStore().capture_dir(chat["modern"], capture_id)
    assert not (d / "run1").exists() and not (d / "run2").exists()
    again = await tools.record_baseline.ainvoke({"capture_id": capture_id, "rule_proposals": lite.PROPOSALS})
    assert "only a complete capture becomes a baseline" in again
    assert await _versions(chat) == []


async def test_a_capture_of_an_older_plan_is_not_recorded(chat, monkeypatch):
    await _approved_inputs(chat)
    await _turn(chat)
    store = LocalBaselineStore()
    capture_id = "cap-20260930000003-dddddd"
    store.write_manifest(chat["modern"], capture_id, {
        "id": capture_id, "status": "complete", "planVersion": 7, "mapping": lite.MAPPING,
        "notCaptured": lite.NOT_CAPTURED, "noise": {}, "finishedAt": "2026-09-30T00:00:00+00:00"})
    out = await tools.record_baseline.ainvoke({"capture_id": capture_id, "rule_proposals": []})
    assert "recorded the criteria of plan v7, but the approved plan is now v1" in out


# ── acceptance and the ledger ───────────────────────────────────────────────

async def _stored_version(env, placements):
    async with get_db_session_for_tenant(env["org"]) as s:
        ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["modern"], stage=STAGE,
                                           payload={"baselines": [], "placements": placements}, produced_by="u-qa")
    return ref.version


async def test_an_acceptance_the_ledger_refuses_rolls_back(chat):
    await _approved_inputs(chat)
    v = await _stored_version(chat, [])
    r = _publish(chat, v, "u-qa2")
    assert r.status_code == 409 and "marks no module on the ledger" in r.json()["detail"]
    v = await _stored_version(chat, [{"module_id": "M-09", "baseline_ids": ["BL-01"]}])
    r = _publish(chat, v, "u-qa2")
    assert r.status_code == 409 and "M-09 is not on the ledger" in r.json()["detail"]
    assert {x.state for x in (await _ledger(chat)).values()} == {"sequenced"}


async def test_a_revised_baseline_updates_a_baselined_module_but_not_one_being_migrated(chat):
    await _approved_inputs(chat)
    v1 = await _stored_version(chat, [{"module_id": "M-01", "baseline_ids": ["BL-01"]},
                                      {"module_id": "M-02", "baseline_ids": ["BL-02"]}])
    assert _publish(chat, v1, "u-qa2").status_code == 200
    async with get_db_session_for_tenant(chat["org"]) as s:
        await ledger.migration_started(s, project_id=chat["modern"], module_id="M-02", target_branch="migrate/m-02",
                                       target_path="batch", actor="u-dev")
    v2 = await _stored_version(chat, [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-04"]},
                                      {"module_id": "M-02", "baseline_ids": ["BL-05"]}])
    r = _publish(chat, v2, "u-qa2")
    assert r.status_code == 409 and "M-02 is already migrating against baselines BL-02" in r.json()["detail"], r.text
    assert (await _ledger(chat))["M-01"].baseline_ids == ["BL-01"], "rolled back, nothing half-applied"
    v3 = await _stored_version(chat, [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-04"]},
                                      {"module_id": "M-02", "baseline_ids": ["BL-02"]}])
    assert _publish(chat, v3, "u-qa2").status_code == 200
    m01 = (await _ledger(chat))["M-01"]
    assert (m01.state, m01.baseline_ids, m01.history[-1]["note"]) == ("baselined", ["BL-01", "BL-04"], "baseline revised")


async def test_a_designed_or_blocked_module_is_not_baselined(chat):
    await _approved_inputs(chat)
    async with get_db_session_for_tenant(chat["org"]) as s:
        await ledger.block(s, project_id=chat["modern"], module_id="M-02", agent="testing_modernization",
                           reason="sandbox image missing", actor="u-qa")
    v = await _stored_version(chat, [{"module_id": "M-02", "baseline_ids": ["BL-01"]}])
    r = _publish(chat, v, "u-qa2")
    assert r.status_code == 409 and "M-02 is blocked (sandbox image missing)" in r.json()["detail"]
