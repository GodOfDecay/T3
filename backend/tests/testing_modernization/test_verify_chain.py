"""Equivalence Testing, Verify mode — through the real tools, database, git and sandbox (Phase J).

ClaimTrack Lite's claims API (M-01): the baseline captured in Docker and accepted (Phase G, for real); the
module migrated to Python 3.12 on a local target (Phase H's tools, the build files moved to a pinned 3.12
image); Review approve and Security PASS on the ledger, so M-01 is `verifying`. QA verifies it: the module
taken from the accepted head and overlaid on the legacy system, run twice, compared with the baseline per
criterion, and EC-04's p95 timed on both sides. Research §6.5's acceptance checks:
  - a faithful migration is VERIFIED (EC-01, EC-02 passed after their own rules; EC-04 measured both sides);
  - a deliberately broken target (the rounding trap left in) is CAUGHT: EC-02 fails on `payout` in the
    half-cent cases, and accepting it sends M-01 back to `migrating`, the difference visible to Migration
    Development;
  - the legacy module replayed against its own baseline gives zero differences;
  - the same replay twice gives the same verdict.
"""
from __future__ import annotations

import json
import re

import pytest

from agents_orchestrator.development_modernization_agent import workspace as W
from agents_orchestrator.development_modernization_agent.sandbox import available as docker_up
from agents_orchestrator.development_modernization_agent.tools import migration_tools as dev
from agents_orchestrator.modernization_common import review_checkout as RC
from agents_orchestrator.testing_modernization_agent.tools import equivalence_tools as eq
from agents_orchestrator.testing_modernization_agent.tools import verify_tools as vt
from config.ws_helper import set_consequential_approved, set_orchestrator_run
from shared.db import get_db_session_for_tenant
from shared.services import modernization_ledger as ledger
from tests.development_modernization.test_chain import (  # noqa: F401 — fixtures
    DOCKERFILE, _client, _ledger, _plan_and_design, _turn, chat, env,
)
from tests.review_security_modernization import lite_i as L
from tests.testing_modernization import lite

pytestmark = [pytest.mark.usefixtures("purge_created_orgs"),
              pytest.mark.skipif(not docker_up(), reason="Docker is not running")]

APPROVE = ["artifact:view", "artifact:approve_development_modernization", "artifact:approve_testing_modernization"]
PERF = {"EC-04": ["claims-read"]}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def venv(chat, monkeypatch):
    import shutil
    monkeypatch.setenv("SDLC_SANDBOX_HEALTH_SECONDS", "15")
    monkeypatch.setattr(vt, "PERF_REPEAT", 5)
    yield chat
    shutil.rmtree(RC.root() / chat["proj"], ignore_errors=True)


def _publish(env, stage, v, user):
    client, hdr = _client(env, user, APPROVE)
    return client.post(f"/artifact-versions/{env['proj']}/stages/{stage}/versions/{v}/publish", json={}, headers=hdr)


async def _baseline(env):
    await _plan_and_design(env, design_payload=L.design())
    await _turn(env, "u-qa", "testing_modernization")
    set_consequential_approved(True)
    out = await eq.capture_baseline.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    capture_id = re.search(r"cap-\d{14}-[0-9a-f]{6}", out).group(0)
    assert "Recorded as baseline v1" in await eq.record_baseline.ainvoke({"capture_id": capture_id,
                                                                          "rule_proposals": lite.PROPOSALS})
    assert _publish(env, "testing_modernization", 1, "u-qa2").status_code == 200
    await _adopt_proposals(env)


async def _adopt_proposals(env):
    """Migration Strategy adopts the baseline's rule proposals (`requestId` is a fresh uuid on every response,
    in the legacy too): plan v2, the same waves and criteria, approved by someone else. Without it verify
    honestly reports a normalization gap on every scenario — what the first run of this test did."""
    import copy
    from shared.services.artifact_versions import publish_version, snapshot_stage_payload
    plan = copy.deepcopy(lite.stored_plan())
    for c in plan["equivalence_criteria"]:
        if c["id"] in {p["ec_id"] for p in lite.PROPOSALS}:
            c["normalization"] = [*(c.get("normalization") or []),
                                  {"field": "requestId", "rule": "ignore the value, require it present",
                                   "reason": "a fresh uuid per response (the baseline's noise report)"}]
    async with get_db_session_for_tenant(env["org"]) as s:
        ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["proj"], stage="strategy",
                                           payload=plan, produced_by="u-arch")
        await publish_version(s, tenant_id=env["org"], project_id=env["proj"], stage="strategy", version=ref.version,
                              published_by="u-pa")


async def _verifying(env, server_text: str, version: int = 1, *, python3: bool = True) -> None:
    """Migrate M-01 as given (record, accept, push), then Review approve + Security PASS on the ledger."""
    await _turn(env)
    if version == 1:
        await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    mdir = W.module_dir(env["proj"], "M-01")
    repo = mdir / "repo"
    (repo / "claims-api" / "server.py").write_text(server_text, encoding="utf-8")
    state = W.read_state(mdir)
    W.commit(repo, state, "fix", f"round {version}")
    if python3:
        (repo / "Dockerfile").write_text(DOCKERFILE)
        (repo / "claims-api" / "runtime.txt").write_text("python-3.12\n")
        W.commit(repo, state, "build", "run on Python 3.12 (pinned)")
    head = W.head(repo)
    state["builds"] = [*state.get("builds", []), {"round": 1, "ok": True, "head": head}]
    state["lint"] = {"status": "green", "head": head}
    W.write_state(mdir, state)
    out = await dev.record_module_migration.ainvoke({"module_id": "M-01", "outcome": "ready_for_review",
                                                     "file_map": L.FILE_MAP, "traps_handled": L.TRAPS})
    assert f"Recorded as migration record v{version}" in out, out
    assert _publish(env, "development_modernization", version, "u-dev2").status_code == 200
    await _turn(env)
    set_consequential_approved(True)
    assert "Pushed" in await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    async with get_db_session_for_tenant(env["org"]) as s:
        ref = ledger.ArtifactRef("migration_review_artifacts", version)
        await ledger.review_submitted(s, project_id=env["proj"], module_id="M-01", verdict="approve", actor="u-arch2", artifact=ref)
        await ledger.security_submitted(s, project_id=env["proj"], module_id="M-01", verdict="PASS", actor="u-pa", artifact=ref)
    assert (await _ledger(env))["M-01"].state == "verifying"


async def _verify(env):
    await _turn(env, "u-qa", "testing_modernization")
    plan = await vt.get_verification_plan.ainvoke({"module_id": "M-01", "perf_mapping": PERF})
    set_consequential_approved(True)
    return plan, await vt.run_verification.ainvoke({"module_id": "M-01", "perf_mapping": PERF})


async def test_a_faithful_migration_is_verified_and_accepting_it_marks_the_module_verified(venv):
    env = venv
    await _baseline(env)
    await _verifying(env, L.migrated_server())
    plan, out = await _verify(env)
    assert "Migration record v1 (accepted)" in plan and "timed: claims-read" in plan and "| EC-02" in plan, plan
    assert "Verification of M-01 — VERIFIED" in out, out
    assert "| EC-01 | passed | 5 |" in out and "| EC-02 | passed | 6 |" in out, out
    assert re.search(r"\| EC-04 \| \d+(\.\d+)? ms \| \d+(\.\d+)? ms \| 250\.0 ms \|", out), out
    for leak in ("Test Claimant", "CLM-000", "0.13", "0.12"):
        assert leak not in out, leak
    # The same replay twice gives the same verdict.
    _plan, again = await _verify(env)
    assert "VERIFIED" in again and "| EC-02 | passed | 6 |" in again
    # Recorded by the QA who ran it; accepted by another.
    out = await vt.record_equivalence_results.ainvoke({"module_id": "M-01"})
    assert "Recorded as verification v2" in out and "as verified on the ledger" in out, out[-400:]
    assert _publish(env, "testing_modernization", 2, "u-qa").status_code == 403
    assert _publish(env, "testing_modernization", 2, "u-qa2").status_code == 200
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.equivalence_verdict, row.perf_verdict) == ("verified", "verified", "passed")
    # The baseline is still the baseline: accepting a verification never superseded it.
    client, hdr = _client(env, "u-qa2", APPROVE)
    v1 = client.get(f"/artifact-versions/{env['proj']}/stages/testing_modernization/versions/1", headers=hdr).json()
    assert v1["status"] == "published"
    packet = client.get(f"/projects/{env['proj']}/modernization/equivalence-testing/versions/2/packet", headers=hdr).json()
    assert packet["ok"] is True and packet["packet"]["payload"]["mode"] == "verify"


async def test_the_rounding_trap_left_in_is_caught_and_sent_back(venv):
    env = venv
    await _baseline(env)
    await _verifying(env, L.broken_server().replace("return self.reply(400,", "return self.reply(409,")
                     .replace('        if self.path == "/metrics":\n            return self.reply(200, {"uptime": 1})\n', ""))
    _plan, out = await _verify(env)
    assert "Verification of M-01 — MIGRATING" in out, out
    assert "| EC-02 | failed | 6 |" in out and "| EC-01 | passed | 5 |" in out, out
    assert re.search(r"\| EQ-\d{3} \| EC-02 \| regression \| settle:payout \| 2 \| <number> vs <number> \| TR-01", out), out
    # The agent cannot wave it through: an accepted change needs an ADR on the module.
    eq_id = re.search(r"\| (EQ-\d{3}) \| EC-02 \| regression", out).group(1)
    refused = await vt.record_equivalence_results.ainvoke({"module_id": "M-01", "accepted_changes": {eq_id: "ADR-09"}})
    assert "not an ADR on this module" in refused, refused
    assert "Recorded as verification v2" in await vt.record_equivalence_results.ainvoke({"module_id": "M-01"})
    assert _publish(env, "testing_modernization", 2, "u-qa2").status_code == 200
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.equivalence_verdict) == ("migrating", "migrating")
    await _turn(env)
    rework = await dev.read_review_findings.ainvoke({"module_id": "M-01"})
    assert "Equivalence verification v2 (accepted): migrating" in rework and "settle:payout differs in 2 case(s)" in rework, rework


async def test_the_legacy_module_against_its_own_baseline_gives_zero_differences(venv):
    env = venv
    await _baseline(env)
    await _verifying(env, L.LEGACY_SERVER, python3=False)
    _plan, out = await _verify(env)
    assert "No difference after each criterion's own normalization." in out, out
    assert "| EC-01 | passed | 5 |" in out and "| EC-02 | passed | 6 |" in out, out


async def test_refusals_before_anything_runs(venv):
    env = venv
    await _baseline(env)
    await _turn(env, "u-qa", "testing_modernization")
    assert "has no migration record" in await vt.get_verification_plan.ainvoke({"module_id": "M-01"})
    await _verifying(env, L.migrated_server())
    await _turn(env, "u-dev", "testing_modernization")
    set_consequential_approved(True)
    assert "Only QA or a Project Admin" in await vt.run_verification.ainvoke({"module_id": "M-01"})
    await _turn(env, "u-qa", "testing_modernization")
    set_consequential_approved(True)
    assert "is not a performance criterion" in await vt.run_verification.ainvoke(
        {"module_id": "M-01", "perf_mapping": {"EC-01": ["claims-read"]}})
    assert "time HTTP scenarios" in await vt.run_verification.ainvoke(
        {"module_id": "M-01", "perf_mapping": {"EC-04": ["bank-file"]}})
    assert "run the verification first" in await vt.record_equivalence_results.ainvoke({"module_id": "M-01"})
    set_orchestrator_run(True)
    assert "verified on the Equivalence Testing page" in await vt.run_verification.ainvoke({"module_id": "M-01"})
    set_orchestrator_run(False)
    await _turn(env, "u-qa", "testing_modernization")
    set_consequential_approved(False)
    out = await vt.run_verification.ainvoke({"module_id": "M-01"})
    assert "NOT DONE" in out or "confirm" in out.lower(), "no consent on this turn"
    assert json.dumps(lite.MAPPING)  # (fixture sanity)
