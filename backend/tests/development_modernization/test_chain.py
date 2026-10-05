"""Migration Development — through the real tools, database, git and sandbox (Phase H).

The whole module migration for ClaimTrack Lite's claims API (M-01), Python 2.7 → 3.12, the way a Developer
drives it: the baseline is captured and accepted (Phase G, for real); the module's plan shows the traps;
the workspace opens on the TARGET (a local repository standing in for GitHub — `SDLC_TARGET_REMOTE_MAP`);
the legacy build is red on the target runtime; the 2to3 recipe makes it build but the preview cannot even
start it under the legacy runtime image; the build commit moves the image to 3.12; the preview then shows
every response failing (the socket needs bytes); the hand fixes handle both traps; the preview is identical
to the baseline; the record is checked, accepted by ANOTHER Developer, and only then pushed — never forced
— with the pull request generated from the record. Around it, every refusal.
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

from agents_orchestrator.development_modernization_agent import workspace as W
from agents_orchestrator.development_modernization_agent.sandbox import available as docker_up
from agents_orchestrator.development_modernization_agent.toolchains import _PYTHON_312
from agents_orchestrator.development_modernization_agent.tools import migration_tools as dev
from agents_orchestrator.modernization_common import legacy_code
from agents_orchestrator.modernization_common.standalone import _chat_run, upstream_from_pages
from agents_orchestrator.modernization_common.versions import reset_built_from
from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore
from agents_orchestrator.testing_modernization_agent.tools import equivalence_tools as eq
from config.auth.jwt import create_access_token
from config.ws_helper import (
    reset_session_id, set_consequential_approved, set_orchestrator_run, set_project_id, set_run_id,
    set_session_id, set_tenant_id, set_user_id,
)
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import modernization_ledger as ledger
from shared.services import repository_roles as rr
from shared.services.artifact_versions import publish_version, snapshot_stage_payload
from tests.development_modernization.lite_h import design
from tests.testing_modernization import lite

pytestmark = pytest.mark.usefixtures("purge_created_orgs")
needs_docker = pytest.mark.skipif(not docker_up(), reason="Docker is not running")

STAGE = "development_modernization"
LEGACY_URL = "https://github.com/claimtrack/claimtrack-lite"
TARGET_URL = "https://github.com/claimtrack/claimtrack-lite-target"
APPROVE = ["artifact:view", "artifact:approve_development_modernization", "artifact:approve_testing_modernization"]

SERVER_FIX_OLD_ROUND = "    return round(amount * rate, 2)"
SERVER_FIX_NEW_ROUND = (
    "    # TR-01: Python 2 round() rounded halves away from zero; Python 3 rounds to even. Keep the\n"
    "    # legacy rule, on the float's exact value (what Python 2 did).\n"
    "    return float(Decimal(amount * rate).quantize(Decimal(\"0.01\"), rounding=ROUND_HALF_UP))")
DOCKERFILE = (f"# ClaimTrack — target runtime (Python 3.12), pinned by digest.\nFROM {_PYTHON_312}\n\nWORKDIR /app\n"
              "COPY claims-api /app/claims-api\nCOPY settlement-batch /app/settlement-batch\nCOPY db /app/db\n\n"
              "ENV CLAIMTRACK_DB=/data/claimtrack.db \\\n    CLAIMTRACK_OUT=/data/out \\\n    FRAUD_URL=http://fraudscore:9000\n\n"
              "EXPOSE 8080\nCMD [\"sh\", \"-c\", \"mkdir -p /data && python db/init.py && python claims-api/server.py\"]\n")
FILE_MAP = [{"legacy_path": f"claims-api/{f}", "disposition": "mapped", "target_path": f"claims-api/{f}"}
            for f in ("requirements.txt", "runtime.txt", "server.py")]
TRAPS = {"TR-01": "claims-api/server.py payout(): Decimal ROUND_HALF_UP on the exact value",
         "TR-02": "claims-api/server.py Handler.reply(): the JSON is encoded to bytes before the socket write"}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def env(tmp_path, monkeypatch):
    org, bu, proj = (str(_uuid.uuid4()) for _ in range(3))
    wiring = {s: ["github"] for s in rr.TRACK3_STAGES}
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseH')"),
                        {"i": org, "s": f"ph-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track, connectors) "
                             "VALUES (:i, :w, :t, 'ClaimTrack Lite', 'modernization', CAST(:c AS jsonb))"),
                        {"i": proj, "w": bu, "t": org, "c": json.dumps(wiring)})
        await s.execute(text("INSERT INTO integration_grants (tenant_id, kind, target_ref, workspace_id) "
                             "VALUES (CAST(:t AS uuid), 'connector', 'github', CAST(:w AS uuid))"), {"t": org, "w": bu})
        for role, url in (("legacy", LEGACY_URL), ("target", TARGET_URL)):
            await rr.set_role(s, tenant_id=org, project_id=proj, role=role, url=url, branch="main", actor="u-pa")
    for user, role in (("u-dev", "developer"), ("u-dev2", "developer"), ("u-pa", "project_admin"), ("u-qa", "qa"),
                       ("u-qa2", "qa"), ("u-arch", "architect")):
        await grant_role(user, proj, role, tenant_id=org, scope_kind="project")
    repo = tmp_path / "claimtrack-lite"
    shutil.copytree(lite.SAMPLE, repo)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "sample"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True)
    assert (await legacy_code.pull_now(proj, repo.resolve().as_uri(), "main", user_id="u-qa"))["status"] == "ready"
    target = tmp_path / "target.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(target)], check=True)
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("SDLC_TARGET_REMOTE_MAP", json.dumps({TARGET_URL: str(target)}))
    yield {"org": org, "proj": proj, "target": target, "legacy_repo": repo}
    shutil.rmtree(legacy_code.project_dir(proj), ignore_errors=True)
    shutil.rmtree(LocalBaselineStore().project_dir(proj), ignore_errors=True)
    shutil.rmtree(W.root() / proj, ignore_errors=True)


async def _plan_and_design(env, *, design_payload=None):
    async with get_db_session_for_tenant(env["org"]) as s:
        for stage, payload in (("design_modernization", design_payload or design()), ("strategy", lite.stored_plan())):
            ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["proj"], stage=stage,
                                               payload=payload, produced_by="u-arch")
            await publish_version(s, tenant_id=env["org"], project_id=env["proj"], stage=stage, version=ref.version,
                                  published_by="u-pa")
        await ledger.design_approved(
            s, tenant_id=env["org"], project_id=env["proj"], actor="u-pa",
            artifact=ledger.ArtifactRef("target_design_artifacts", 1),
            modules=[{"module_id": m, "module_name": p, "legacy_path": p, "patterns": lite.DESIGNED[m]}
                     for m, p in (("M-01", "claims-api"), ("M-02", "settlement-batch"))])
        await ledger.strategy_approved(
            s, project_id=env["proj"], actor="u-pa", artifact=ledger.ArtifactRef("strategy_artifacts", 1),
            placements=[{"module_id": "M-01", "wave": "W1", "patterns": lite.DESIGNED["M-01"],
                         "ec_ids": ["EC-01", "EC-02", "EC-04"]},
                        {"module_id": "M-02", "wave": "W2", "patterns": lite.DESIGNED["M-02"], "ec_ids": ["EC-03"]}])


async def _paper_baseline(env):
    """An ACCEPTED baseline without running the legacy system (for the tests that never preview)."""
    placements = [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-02"]}, {"module_id": "M-02", "baseline_ids": ["BL-03"]}]
    async with get_db_session_for_tenant(env["org"]) as s:
        ref = await snapshot_stage_payload(s, tenant_id=env["org"], project_id=env["proj"], stage="testing_modernization",
                                           payload={"mode": "baseline", "baselines": [], "placements": placements,
                                                    "mapping": lite.MAPPING}, produced_by="u-qa")
        await publish_version(s, tenant_id=env["org"], project_id=env["proj"], stage="testing_modernization",
                              version=ref.version, published_by="u-qa2")
        await ledger.baselines_approved(s, project_id=env["proj"], placements=placements, actor="u-qa2",
                                        artifact=ledger.ArtifactRef("equivalence_artifacts", ref.version))


def _bind(env, user, stage):
    set_tenant_id(env["org"])
    set_project_id(env["proj"])
    set_user_id(user)
    set_orchestrator_run(False)
    set_consequential_approved(False)


async def _turn(env, user="u-dev", stage=STAGE):
    _bind(env, user, stage)
    set_session_id(f"s-{stage[:4]}-{env['proj'][:8]}")
    set_run_id(await _chat_run(env["org"], env["proj"], stage))
    reset_built_from()
    await upstream_from_pages(env["proj"], env["org"], stage, consumed_by=user,
                              consumer_session=f"s-{stage[:4]}-{env['proj'][:8]}")


@pytest.fixture
async def chat(env):
    token = set_session_id("init")
    yield env
    reset_built_from()
    reset_session_id(token)
    set_consequential_approved(False)
    for fn in (set_tenant_id, set_project_id, set_run_id):
        fn(None)
    set_user_id("")


@pytest.fixture
def audited(monkeypatch):
    from shared.audit.service import audit_service
    events = []

    async def emit(payload):
        events.append(payload)

    monkeypatch.setattr(audit_service, "emit", emit)
    return events


async def _ledger(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        return {r.module_id: r for r in await ledger.list_modules(s, env["proj"])}


def _client(env, user, perms=APPROVE):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=perms)}


def _publish(env, stage, v, user):
    client, hdr = _client(env, user)
    return client.post(f"/artifact-versions/{env['proj']}/stages/{stage}/versions/{v}/publish", json={}, headers=hdr)


def _bare_log(env, ref):
    return subprocess.run(["git", "--git-dir", str(env["target"]), "log", "--reverse", "--format=%s", ref],
                          capture_output=True, text=True).stdout.splitlines()


async def _capture_and_accept_baseline(env):
    """Phase G for real: QA captures and records; a second QA accepts — M-01 and M-02 become baselined."""
    await _turn(env, "u-qa", "testing_modernization")
    set_consequential_approved(True)
    out = await eq.capture_baseline.ainvoke({"mapping": lite.MAPPING, "not_captured": lite.NOT_CAPTURED})
    capture_id = re.search(r"cap-\d{14}-[0-9a-f]{6}", out).group(0)
    done = await eq.record_baseline.ainvoke({"capture_id": capture_id, "rule_proposals": lite.PROPOSALS})
    assert "Recorded as baseline v1" in done, done[-300:]
    assert _publish(env, "testing_modernization", 1, "u-qa2").status_code == 200


# ── the whole module, for real ──────────────────────────────────────────────

@needs_docker
async def test_a_module_is_migrated_previewed_recorded_accepted_and_pushed(chat, audited, monkeypatch):
    env = chat
    monkeypatch.setenv("SDLC_SANDBOX_HEALTH_SECONDS", "15")
    await _plan_and_design(env)
    await _capture_and_accept_baseline(env)
    await _turn(env)

    plan = await dev.get_module_plan.ainvoke({"module_id": "M-01"})
    assert "ACCEPTED, BL-01, BL-02" in plan and "TR-01 Python 3 round()" in plan and "TR-02 Python 3 separates" in plan
    assert "Python 2.7 → Java 21 · Node 24 · Python 3.12" in plan and "toolchain available: python" in plan

    # The wave starts in the future: said, and started only on an explicit override.
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-01"})
    assert "wave W1 starts 2026-12-01" in out, out
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    assert "Workspace open for M-01 on branch `migrate/claims-api`" in out and "empty until now" in out, out
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.target_branch, row.target_path) == ("migrating", "migrate/claims-api", "claims-api")

    # Round 1: the legacy code on the target runtime — honestly red.
    out = await dev.run_build.ainvoke({"module_id": "M-01"})
    assert "Build round 1 of 5: RED" in out and "cannot import BaseHTTPServer" in out, out
    assert "2to3: lib2to3 CPython 3.12" in await dev.list_upgrade_recipes.ainvoke({"module_id": "M-01"})
    out = await dev.run_upgrade_recipe.ainvoke({"module_id": "M-01", "recipe_id": "2to3"})
    assert "changed 1 file(s), committed as a recipe commit" in out and "claims-api/server.py" in out, out
    assert "Build round 2 of 5: GREEN" in await dev.run_build.ainvoke({"module_id": "M-01"})

    # The preview cannot even start the module under the LEGACY image: the build commit is needed.
    out = await dev.preview_equivalence.ainvoke({"module_id": "M-01"})
    assert "could not run the migrated system" in out and "its container is exited" in out, out
    assert (await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "Dockerfile", "content": DOCKERFILE})).startswith("Wrote Dockerfile")
    await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/runtime.txt", "content": "python-3.12\n"})
    await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/requirements.txt",
                                         "content": "# Python 3.12 standard library only: nothing to install.\n"})
    out = await dev.commit_changes.ainvoke({"module_id": "M-01", "concern": "build", "message": "run on Python 3.12 (pinned)"})
    assert out.startswith("Committed") and "Still uncommitted" not in out, out
    assert "Build round 3 of 5: GREEN" in await dev.run_build.ainvoke({"module_id": "M-01"})

    # Under 3.12 it starts — and answers nothing, not even /health: the socket needs bytes (TR-02).
    out = await dev.preview_equivalence.ainvoke({"module_id": "M-01"})
    assert "The service with the migrated module did not answer on /health" in out and "container is running" in out, out

    # Hand fix 1: bytes on the socket (TR-02) — the rounding trap (TR-01) still in place. The preview must
    # catch exactly the half-cent payouts (CLM-0004, CLM-0007) and nothing else: a broken target is caught.
    await dev.edit_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/server.py",
                                        "old": "        self.wfile.write(data)", "new": "        self.wfile.write(data.encode(\"utf-8\"))"})
    assert (await dev.commit_changes.ainvoke({"module_id": "M-01", "concern": "fix",
                                              "message": "TR-02 bytes on the socket"})).startswith("Committed")
    assert "Build round 4 of 5: GREEN" in await dev.run_build.ainvoke({"module_id": "M-01"})
    out = await dev.preview_equivalence.ainvoke({"module_id": "M-01"})
    assert "| claims-read | 5 | none — identical after normalization |" in out, out
    assert "| settle | 6 | payout (2; <number> vs <number>) |" in out, out
    for leak in ("Test Claimant", "CLM-000", "0.13", "0.12"):
        assert leak not in out, leak

    # Hand fix 2: the legacy rounding kept (TR-01).
    await dev.edit_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/server.py",
                                        "old": SERVER_FIX_OLD_ROUND, "new": SERVER_FIX_NEW_ROUND})
    await dev.edit_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/server.py",
                                        "old": "import uuid\n", "new": "import uuid\nfrom decimal import Decimal, ROUND_HALF_UP\n"})
    assert (await dev.commit_changes.ainvoke({"module_id": "M-01", "concern": "fix",
                                              "message": "TR-01 legacy rounding kept"})).startswith("Committed")
    assert "Build round 5 of 5: GREEN" in await dev.run_build.ainvoke({"module_id": "M-01"})
    assert "not run" in await dev.run_tests.ainvoke({"module_id": "M-01"})
    assert "Lint: GREEN" in await dev.run_lint.ainvoke({"module_id": "M-01"})
    out = await dev.preview_equivalence.ainvoke({"module_id": "M-01"})
    assert "| claims-read | 5 | none — identical after normalization |" in out, out
    assert "| settle | 6 | none — identical after normalization |" in out, out

    # Recording: an incomplete map and an unhandled trap are refused, then the real record.
    out = await dev.record_module_migration.ainvoke({"module_id": "M-01", "outcome": "ready_for_review",
                                                     "file_map": FILE_MAP[:2], "traps_handled": {"TR-01": "x"}})
    assert out.startswith("NOT RECORDED") and "Missing: claims-api/server.py" in out and "TR-02" in out, out
    out = await dev.record_module_migration.ainvoke({
        "module_id": "M-01", "outcome": "ready_for_review", "file_map": FILE_MAP, "traps_handled": TRAPS,
        "llm_rewritten": [{"file": "claims-api/server.py", "reason": "legacy rounding kept (TR-01); bytes on the socket (TR-02)"}],
        "manual_follow_ups": ["settlement-batch (M-02) still runs Python 2 code: the shared image moves with it in W2"]})
    assert "Recorded as migration record v1" in out and "build green" in out and "11 case(s) identical" in out, out[-500:]

    # Pushing: needs acceptance by someone else, then this turn's yes.
    set_consequential_approved(True)
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert "is not accepted yet" in out, out
    assert _publish(env, STAGE, 1, "u-dev").status_code == 403, "the producer cannot accept it"
    assert _publish(env, STAGE, 1, "u-dev2").status_code == 200
    await _turn(env)
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert "NOT DONE" in out or "confirm" in out.lower(), "no consent on this turn"
    assert _bare_log(env, "migrate/claims-api") == []
    set_consequential_approved(True)
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert "Pushed `migrate/claims-api`" in out and "#pull/1" in out and "now in review" in out, out

    # The target holds exactly the accepted branch, commits by concern; the legacy was never written.
    subjects = _bare_log(env, "migrate/claims-api")
    assert [s.split(":", 1)[0] for s in subjects] == ["Start main for the migration", "copy", "recipe", "build", "fix", "fix"]
    prs = json.loads((env["target"] / "sdlc-pull-requests.json").read_text())
    assert prs[0]["head"] == "migrate/claims-api" and prs[0]["base"] == "main"
    assert "TR-01: claims-api/server.py payout()" in prs[0]["body"] and "| `claims-api/server.py` | mapped |" in prs[0]["body"]
    legacy_status = subprocess.run(["git", "status", "--porcelain"], cwd=env["legacy_repo"], capture_output=True, text=True)
    assert legacy_status.stdout == "" and (env["legacy_repo"] / "claims-api" / "server.py").read_bytes() == \
        (lite.SAMPLE / "claims-api" / "server.py").read_bytes()
    row = (await _ledger(env))["M-01"]
    assert row.state == "in_review" and row.pr_url == prs[0]["url"]
    assert row.history[-1]["artifact"] == {"stage": "migration_artifacts", "version": 1}
    assert [e.event_type for e in audited if e.event_type.startswith("modernization.migration")] == [
        "modernization.migration_started", "modernization.migration_recorded", "modernization.migration_pushed"]

    # The page: workspaces (no code), the packet, the export.
    client, hdr = _client(env, "u-dev2")
    ws = client.get(f"/projects/{env['proj']}/modernization/migration-development/workspaces", headers=hdr).json()
    m = ws["workspaces"][0]
    assert [b["ok"] for b in m["builds"]] == [False, True, True, True, True] and m["lint"] == "green" and m["tests"] == "not_run"
    assert "ROUND_HALF_UP" not in json.dumps(ws), "the page never gets code"
    packet = client.get(f"/projects/{env['proj']}/modernization/migration-development/versions/1/packet", headers=hdr).json()
    assert packet["ok"] is True and packet["packet"]["payload"]["build"] == {"status": "green", "rounds": 5, "failing": None}
    export = client.get(f"/projects/{env['proj']}/modernization/migration-development/versions/1/export?format=docx", headers=hdr)
    assert export.status_code == 200 and export.headers["content-disposition"].endswith('migration-m-01-v1.docx"')


# ── refusals (no Docker) ────────────────────────────────────────────────────

async def test_no_workspace_before_the_baseline_is_accepted(chat):
    await _plan_and_design(chat)
    await _turn(chat)
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    assert "baseline is not accepted" in out and "nothing can prove the migration" in out
    assert "NOT accepted" in await dev.get_module_plan.ainvoke({"module_id": "M-01"})
    assert not (W.root() / chat["proj"]).exists()


async def test_only_a_developer_or_project_admin_of_this_project_migrates(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    for user in ("u-qa", "u-arch"):
        await _turn(chat, user)
        out = await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
        assert out.startswith("Only a Developer or a Project Admin of this project"), (user, out)
    await _turn(chat, "u-pa")
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    assert out.startswith("Workspace open"), out


async def test_an_orchestrator_conversation_explains_but_does_not_migrate(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    await _turn(chat)
    set_orchestrator_run(True)
    try:
        for t, args in ((dev.open_target_workspace, {"module_id": "M-01"}), (dev.push_and_open_pr, {"module_id": "M-01"}),
                        (dev.write_target_file, {"module_id": "M-01", "path": "claims-api/x.py", "content": "x"})):
            assert "migrated on the Migration Development page" in await t.ainvoke(args)
    finally:
        set_orchestrator_run(False)


async def test_no_target_repository_is_said_with_who_sets_it(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    async with get_db_session_for_tenant(chat["org"]) as s:
        await s.execute(text("DELETE FROM project_repositories WHERE project_id = :p AND role = 'target'"), {"p": chat["proj"]})
    await _turn(chat)
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    assert "No target repository is set for this project. A Project Admin sets it" in out


async def test_a_manual_module_is_not_migrated_but_blocked_with_the_hand_off(chat):
    d = design()
    next(m for m in d["modules"] if m["module_id"] == "M-02")["tier"] = "manual"
    await _plan_and_design(chat, design_payload=d)
    async with get_db_session_for_tenant(chat["org"]) as s:
        await s.execute(text("UPDATE modernization_modules SET tier = NULL WHERE project_id = :p"), {"p": chat["proj"]})
    await _paper_baseline(chat)
    await _turn(chat)
    out = await dev.open_target_workspace.ainvoke({"module_id": "M-02", "override_wave_order": True})
    assert "MANUAL tier" in out
    out = await dev.record_module_migration.ainvoke({"module_id": "M-02", "outcome": "blocked",
                                                     "file_map": [{"legacy_path": "settlement-batch/run.py",
                                                                   "disposition": "mapped", "target_path": "x"}]})
    assert out.startswith("NOT RECORDED"), "a blocked module writes no code: no file map"
    out = await dev.record_module_migration.ainvoke({"module_id": "M-02", "outcome": "blocked",
                                                     "handoff_note": "The bank file format is owned by the bank's spec v7; "
                                                                     "a person must redesign the writer."})
    assert "Recorded as migration record v1" in out, out
    row = (await _ledger(chat))["M-02"]
    assert row.state == "blocked" and "bank's spec v7" in row.blocked_reason


async def test_writes_stay_in_the_module_carry_no_secret_and_commits_keep_concerns_apart(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    await _turn(chat)
    assert (await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})).startswith("Workspace open")
    out = await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "settlement-batch/run.py", "content": "x"})
    assert "outside this module (claims-api/)" in out
    out = await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/config.py",
                                               "content": "DB = 'Server=db;User Id=sa;Password=Hunter2!;'\n"})
    assert out.startswith("NOT WRITTEN") and "a connection string with a password" in out and "Hunter2" not in out
    repo = W.module_dir(chat["proj"], "M-01") / "repo"
    assert not (repo / "claims-api" / "config.py").exists()
    await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/runtime.txt", "content": "python-3.12\n"})
    await dev.write_target_file.ainvoke({"module_id": "M-01", "path": "claims-api/server.py", "content": "x = 1\n"})
    out = await dev.commit_changes.ainvoke({"module_id": "M-01", "concern": "fix", "message": "port"})
    assert "Still uncommitted (another concern): claims-api/runtime.txt" in out
    assert "concern is build" in await dev.commit_changes.ainvoke({"module_id": "M-01", "concern": "tidy", "message": "x"})
    out = await dev.run_build.ainvoke({"module_id": "M-01"})
    assert out.startswith("There are uncommitted changes"), "a build round describes a commit"


async def test_the_build_loop_stops_after_five_rounds(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    await _turn(chat)
    await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    mdir = W.module_dir(chat["proj"], "M-01")
    state = W.read_state(mdir)
    state["builds"] = [{"round": n, "ok": False, "failing": "x", "head": "h"} for n in range(1, 6)]
    W.write_state(mdir, state)
    out = await dev.run_build.ainvoke({"module_id": "M-01"})
    assert out.startswith("Five build rounds are used (still red last)")
    out = await dev.record_module_migration.ainvoke({"module_id": "M-01", "outcome": "ready_for_review",
                                                     "file_map": FILE_MAP, "traps_handled": TRAPS})
    assert "only a module whose build is green goes for review" in out


async def test_a_push_needs_the_accepted_record_exactly_and_a_writable_target(chat):
    await _plan_and_design(chat)
    await _paper_baseline(chat)
    await _turn(chat)
    await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    mdir = W.module_dir(chat["proj"], "M-01")
    repo = mdir / "repo"
    state = W.read_state(mdir)
    head = W.head(repo)
    state["builds"] = [{"round": 1, "ok": True, "head": head}]
    state["lint"] = {"status": "green", "head": head}
    W.write_state(mdir, state)
    out = await dev.record_module_migration.ainvoke({"module_id": "M-01", "outcome": "ready_for_review",
                                                     "file_map": FILE_MAP, "traps_handled": TRAPS})
    assert "Recorded as migration record v1" in out, out
    assert _publish(chat, STAGE, 1, "u-dev2").status_code == 200
    await _turn(chat)
    set_consequential_approved(True)
    # A change after acceptance: what is pushed must be exactly what was accepted.
    (repo / "claims-api" / "server.py").write_text("x = 2\n")
    W.commit(repo, state, "fix", "late change")
    W.write_state(mdir, state)
    assert "has changed since the accepted record" in await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    W.git(repo, "reset", "-q", "--hard", head)  # (test only: put the branch back)
    # A read-only wiring of the stage: the platform's chain refuses the write.
    async with get_db_session_for_tenant(chat["org"]) as s:
        await s.execute(text("UPDATE projects SET tool_access_modes = CAST(:m AS jsonb) WHERE id = :p"),
                        {"m": json.dumps({f"{STAGE}::connector::github": "read"}), "p": chat["proj"]})
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert out.startswith("NOT PUSHED") and "has no write access to github" in out, out
    assert _bare_log(chat, "migrate/claims-api") == []
    async with get_db_session_for_tenant(chat["org"]) as s:
        await s.execute(text("UPDATE projects SET tool_access_modes = '{}'::jsonb WHERE id = :p"), {"p": chat["proj"]})
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert "Pushed `migrate/claims-api`" in out, out
    # A second push of an unchanged, already-in-review module is not a new pull request.
    assert "is in_review; a pull request is opened while it is migrating" in await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
