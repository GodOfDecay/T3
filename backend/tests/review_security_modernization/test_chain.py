"""Migration Review and Security — through the real tools, database, git and scanners (Phase I).

ClaimTrack Lite's claims API (M-01) migrated to Python 3.12 and in review (Phase H's tools, its pull request
on a local repository standing in for GitHub). The Architect's review reads both sides, is refused until it
answers every contract, trap, criterion and legacy file and cites only what it opened, and is accepted by
someone else — which records `approve` on the ledger. Security scans both sides with the pinned scanners,
diffs them, checks secrets and authorization, and its accepted PASS moves the module to `verifying`.

The rework loop: a broken migration (the rounding trap left in, a status code changed, a route added) is
caught by the diff, the review that says so is accepted, and the module goes back to `migrating`. A review
of an older migration record can never move a reworked module on.
"""
from __future__ import annotations

import pytest

from agents_orchestrator.code_review_modernization_agent.tools import review_tools as rv
from agents_orchestrator.development_modernization_agent import workspace as W
from agents_orchestrator.development_modernization_agent.tools import migration_tools as dev
from agents_orchestrator.modernization_common import review_checkout as RC
from agents_orchestrator.security_modernization_agent import scanners as S
from agents_orchestrator.security_modernization_agent.tools import security_tools as sec
from config.ws_helper import set_orchestrator_run
from shared.authz.grant import grant_role
from tests.development_modernization.test_chain import (  # noqa: F401 — fixtures
    _client, _ledger, _paper_baseline, _plan_and_design, _turn, audited, chat, env,
)
from tests.review_security_modernization import lite_i as L
from tests.review_security_modernization.test_scanners import _CACHE

pytestmark = pytest.mark.usefixtures("purge_created_orgs")
needs_docker = pytest.mark.skipif(S.available() is not None, reason="Docker is not running")

REVIEW, SECURITY = "code_review_modernization", "security_modernization"
APPROVE = ["artifact:view", "artifact:approve_development_modernization", "artifact:approve_code_review_modernization",
           "artifact:approve_security_modernization"]
LEGACY_FILES = ["claims-api/requirements.txt", "claims-api/runtime.txt", "claims-api/server.py"]


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def review_env(chat):
    for user, role in (("u-arch2", "architect"), ("u-sec", "security_engineer"), ("u-sec2", "security_engineer")):
        await grant_role(user, chat["proj"], role, tenant_id=chat["org"], scope_kind="project")
    yield chat
    import shutil
    shutil.rmtree(RC.root() / chat["proj"], ignore_errors=True)
    shutil.rmtree(W.root() / chat["proj"], ignore_errors=True)


def _publish(env, stage, v, user):
    client, hdr = _client(env, user, APPROVE)
    return client.post(f"/artifact-versions/{env['proj']}/stages/{stage}/versions/{v}/publish", json={}, headers=hdr)


async def _record(env, server_text: str, version: int) -> None:
    """Write the module as given, mark it built (the build itself is Phase H's, tested there), record it and
    have another Developer accept it."""
    await _turn(env)
    mdir = W.module_dir(env["proj"], "M-01")
    repo = mdir / "repo"
    (repo / "claims-api" / "server.py").write_text(server_text, encoding="utf-8")
    (repo / "claims-api" / "runtime.txt").write_text("python-3.12\n")
    state = W.read_state(mdir)
    W.commit(repo, state, "fix", f"migration round {version}")
    W.commit(repo, state, "build", "run on Python 3.12")
    head = W.head(repo)
    state["builds"] = [*state.get("builds", []), {"round": len(state.get("builds", [])) + 1, "ok": True, "head": head}]
    state["lint"] = {"status": "green", "head": head}
    W.write_state(mdir, state)
    out = await dev.record_module_migration.ainvoke({"module_id": "M-01", "outcome": "ready_for_review",
                                                     "file_map": L.FILE_MAP, "traps_handled": L.TRAPS})
    assert f"Recorded as migration record v{version}" in out, out
    assert _publish(env, "development_modernization", version, "u-dev2").status_code == 200


async def _in_review(env, server_text: str, version: int = 1) -> None:
    from config.ws_helper import set_consequential_approved
    if version == 1:
        await _plan_and_design(env, design_payload=L.design())
        await _paper_baseline(env)
        await _turn(env)
        await dev.open_target_workspace.ainvoke({"module_id": "M-01", "override_wave_order": True})
    await _record(env, server_text, version)
    await _turn(env)
    set_consequential_approved(True)
    out = await dev.push_and_open_pr.ainvoke({"module_id": "M-01"})
    assert "Pushed `migrate/claims-api`" in out, out
    assert (await _ledger(env))["M-01"].state == "in_review"


def _checks(contract_note="The response body is the same JSON; it is encoded to bytes for the socket (TR-02)."):
    return {
        "contract_check": [{"ct_id": "CT-01", "status": "unchanged", "note": contract_note}],
        "trap_check": [{"tr_id": "TR-01", "status": "handled", "where": "claims-api/server.py:28"},
                       {"tr_id": "TR-02", "status": "handled", "where": "claims-api/server.py:53"}],
        "equivalence_coverage": [{"ec_id": e, "status": "covered", "note": ""} for e in ("EC-01", "EC-02", "EC-04")],
        "traceability": [{"legacy_path": f, "target_path": f, "status": "mapped"} for f in LEGACY_FILES],
    }


# ── review, then security, then verifying ──────────────────────────────────

async def test_a_faithful_migration_is_reviewed_side_by_side_approved_and_accepted(review_env, audited):
    env = review_env
    await _in_review(env, L.migrated_server())
    await _turn(env, "u-arch", REVIEW)

    out = await rv.TOOLS[1].ainvoke({"module_id": "M-01"})   # read_module_migration
    assert "Migration record v1 (accepted)" in out and "CT-01 /api/v1 claims API" in out and "TR-01" in out, out
    assert "#pull/1" in out and "Ledger: **in_review**" in out
    listing = await rv.TOOLS[2].ainvoke({"module_id": "M-01"})
    assert "| `claims-api/server.py` | `claims-api/server.py` |" in listing

    # Nothing opened yet: refused, whatever the recommendation.
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "s", "merge_recommendation": "approve",
                                                    **_checks()})
    assert out.startswith("NOT SUBMITTED") and "No migrated file was opened" in out, out

    assert "ROUND_HALF_UP" in await rv.TOOLS[3].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    assert "return round(amount * rate, 2)" in await rv.TOOLS[4].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    assert "outside" not in await rv.TOOLS[3].ainvoke({"module_id": "M-01", "path": "../../etc/passwd"})

    surface = await rv.compare_api_surface.ainvoke({"module_id": "M-01"})
    assert "added encoding `utf-8`" in surface and "status" not in surface.split("## Frozen contracts")[1], surface
    anti = await rv.detect_legacy_antipatterns.ainvoke({"module_id": "M-01"})
    assert "0 introduced, 1 carried over), 2 fixed" in anti, anti

    # The contract's file changed in a contract-bearing way: "unchanged" needs the reason.
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "s", "merge_recommendation": "approve",
                                                    **_checks(contract_note="")})
    assert "CT-01 is marked unchanged, but its file changed: added encoding `utf-8`" in out, out
    # A high finding cannot be approved.
    high = {"id": "F-001", "severity": "high", "category": "behaviour_change", "file": "claims-api/server.py", "line": 30,
            "legacy_file": "claims-api/server.py", "legacy_line": 28, "description": "d", "recommendation": "r"}
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "s", "merge_recommendation": "approve",
                                                    "findings": [high], **_checks()})
    assert "force request_changes" in out, out
    debt = [{"pattern": "Hard-coded host", "legacy_file": "claims-api/server.py", "note": "FRAUD_URL default, env overrides"}]
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "Faithful port; both traps handled.",
                                                    "merge_recommendation": "approve", "known_debt": debt, **_checks()})
    assert "**Recommendation: Approve**" in out and "Recorded as migration review v1" in out, out[-400:]
    assert "Files read: 1 target, 1 legacy" in out

    # Accepted by someone who did not produce it — and only then on the ledger.
    assert (await _ledger(env))["M-01"].review_verdict is None
    assert _publish(env, REVIEW, 1, "u-arch").status_code == 403
    assert _publish(env, REVIEW, 1, "u-arch2").status_code == 200
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.review_verdict) == ("in_review", "approve")
    assert row.history[-1]["artifact"] == {"stage": "migration_review_artifacts", "version": 1}

    client, hdr = _client(env, "u-arch2", APPROVE)
    packet = client.get(f"/projects/{env['proj']}/modernization/migration-review/versions/1/packet", headers=hdr).json()
    assert packet["ok"] is True and packet["packet"]["payload"]["files_read"] == {
        "target": ["claims-api/server.py"], "legacy": ["claims-api/server.py"]}
    latest = client.get(f"/projects/{env['proj']}/modernization/migration-review", headers=hdr).json()
    assert latest["payload"]["merge_recommendation"] == "approve"
    assert [e.event_type for e in audited if e.event_type == "modernization.review_submitted"] == ["modernization.review_submitted"]


@needs_docker
async def test_security_scans_both_sides_and_its_accepted_pass_moves_the_module_to_verifying(review_env, monkeypatch):
    env = review_env
    monkeypatch.setenv("SDLC_TRIVY_CACHE", _CACHE)
    await _in_review(env, L.migrated_server())
    await _turn(env, "u-sec", SECURITY)
    out = await sec.scan_migrated_module.ainvoke({"module_id": "M-01"})
    assert "| semgrep 1.99.0 | ran |" in out and "| gitleaks 8.21.2 | ran |" in out, out
    trivy_ran = "| trivy 0.58.1 | ran |" in out
    out = await sec.submit_security_report.ainvoke({"module_id": "M-01", "verdict": "PASS", "rationale": "r"})
    assert "Scan the legacy module first" in out, out
    out = await sec.scan_legacy_baseline.ainvoke({"module_id": "M-01"})
    assert "Scan of the legacy M-01" in out and "from the cache" not in out
    if trivy_ran:
        assert "from the cache" in await sec.scan_legacy_baseline.ainvoke({"module_id": "M-01"})
    diff = await sec.diff_findings.ainvoke({"module_id": "M-01"})
    assert "0 introduced" in diff, diff
    assert "No legacy secret value appears" in await sec.check_secret_carryover.ainvoke({"module_id": "M-01"})
    authz = await sec.check_contract_authz.ainvoke({"module_id": "M-01"})
    assert "CT-01" in authz and "looks **same**" in authz and "no authentication marker on either side" in authz, authz

    weaker = [{"ct_id": "CT-01", "status": "weaker", "note": ""}]
    out = await sec.submit_security_report.ainvoke({"module_id": "M-01", "verdict": "PASS", "rationale": "r",
                                                    "contract_authz": weaker})
    assert "the policy gives FAIL" in out, out
    authz_ok = [{"ct_id": "CT-01", "status": "same", "note": "no authentication on either side, as before"}]
    out = await sec.submit_security_report.ainvoke({
        "module_id": "M-01", "verdict": "PASS" if trivy_ran else "CONDITIONAL", "contract_authz": authz_ok,
        "rationale": "Nothing introduced; the migration removed both Python 2 only modules."})
    if not trivy_ran:  # no database on this machine: never PASS, and said so
        pytest.skip("Trivy's database is not on this machine; PASS is refused without it (unit-tested)")
    assert "**Verdict: PASS**" in out and "Recorded as security report v1" in out, out[-500:]

    assert _publish(env, SECURITY, 1, "u-sec").status_code == 403
    assert _publish(env, SECURITY, 1, "u-sec2").status_code == 200
    assert (await _ledger(env))["M-01"].security_verdict == "PASS"
    await _turn(env, "u-arch", REVIEW)
    await rv.TOOLS[3].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    await rv.TOOLS[4].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "ok", "merge_recommendation": "approve",
                                                    **_checks()})
    assert "Recorded as migration review v1" in out, out
    assert _publish(env, REVIEW, 1, "u-arch2").status_code == 200
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.review_verdict, row.security_verdict) == ("verifying", "approve", "PASS")


async def test_without_scanners_the_report_cannot_pass(review_env, monkeypatch):
    env = review_env
    await _in_review(env, L.migrated_server())
    monkeypatch.setattr(S, "available", lambda: "Docker is not running on this server.")
    await _turn(env, "u-sec", SECURITY)
    out = await sec.scan_migrated_module.ainvoke({"module_id": "M-01"})
    assert out.count("not installed") == 3 and "not scanned" in out, out
    await sec.scan_legacy_baseline.ainvoke({"module_id": "M-01"})
    await sec.check_secret_carryover.ainvoke({"module_id": "M-01"})
    await sec.check_contract_authz.ainvoke({"module_id": "M-01"})
    out = await sec.submit_security_report.ainvoke({"module_id": "M-01", "verdict": "PASS", "rationale": "r",
                                                    "contract_authz": [{"ct_id": "CT-01", "status": "same"}]})
    assert "cannot PASS: trivy, semgrep, gitleaks did not run" in out, out


# ── the rework loop ─────────────────────────────────────────────────────────

async def test_a_broken_migration_is_caught_sent_back_and_a_stale_review_cannot_move_it_on(review_env):
    env = review_env
    await _in_review(env, L.broken_server())
    await _turn(env, "u-arch", REVIEW)
    surface = await rv.compare_api_surface.ainvoke({"module_id": "M-01"})
    assert "removed status `409`" in surface and "added http_path `/metrics`" in surface, surface
    await rv.TOOLS[3].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    await rv.TOOLS[4].ainvoke({"module_id": "M-01", "path": "claims-api/server.py"})
    findings = [
        {"id": "F-001", "severity": "high", "category": "trap_unhandled", "file": "claims-api/server.py", "line": 27,
         "legacy_file": "claims-api/server.py", "legacy_line": 27, "refs": ["TR-01", "EC-02"],
         "description": "Python 3 round() rounds halves to even; CLM-0004 and CLM-0007 pay a cent less.",
         "recommendation": "Decimal ROUND_HALF_UP on the exact value."},
        {"id": "F-002", "severity": "high", "category": "contract_drift", "file": "claims-api/server.py", "line": 84,
         "legacy_file": "claims-api/server.py", "legacy_line": 82, "refs": ["CT-01"],
         "description": "A settled claim answers 400, not 409.", "recommendation": "Answer 409 as before."},
        {"id": "F-003", "severity": "medium", "category": "scope_creep", "file": "claims-api/server.py", "line": 60,
         "description": "/metrics was added; nothing asked for it.", "recommendation": "Remove it."}]
    checks = _checks()
    checks["contract_check"] = [{"ct_id": "CT-01", "status": "changed", "note": "409 → 400"}]
    checks["trap_check"][0] = {"tr_id": "TR-01", "status": "not_handled", "where": ""}
    checks["equivalence_coverage"][1] = {"ec_id": "EC-02", "status": "at_risk", "note": "rounding"}
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "Rounding and a status changed.",
                                                    "merge_recommendation": "request_changes", "findings": findings, **checks})
    assert "**Recommendation: Request changes**" in out and "Findings: 2 high, 1 medium" in out, out[-300:]
    # A second review of the same (old) migration, left unaccepted.
    out = await rv.submit_migration_review.ainvoke({"module_id": "M-01", "summary": "again",
                                                    "merge_recommendation": "request_changes", "findings": findings, **checks})
    assert "Recorded as migration review v2" in out, out[-200:]

    assert _publish(env, REVIEW, 1, "u-arch2").status_code == 200
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.review_verdict, row.rejection_count) == ("migrating", "request_changes", 1)

    # Migration Development reworks it: record v2, accepted, pushed (the same pull request).
    await _in_review(env, L.migrated_server(), version=2)
    out = _publish(env, REVIEW, 2, "u-arch2")
    assert out.status_code == 409 and "has been migrated again since (v2)" in out.json()["detail"], out.text
    row = (await _ledger(env))["M-01"]
    assert (row.state, row.review_verdict) == ("in_review", None)

    # The review of the reworked module reads the new head.
    await _turn(env, "u-arch", REVIEW)
    assert "Migration record v2 (accepted)" in await rv.TOOLS[1].ainvoke({"module_id": "M-01"})


# ── who may, and where ──────────────────────────────────────────────────────

async def test_only_the_owners_submit_and_never_from_an_orchestrator_conversation(review_env):
    env = review_env
    await _in_review(env, L.migrated_server())
    await _turn(env, "u-dev", REVIEW)
    assert "Only an Architect or a Project Admin" in await rv.submit_migration_review.ainvoke(
        {"module_id": "M-01", "summary": "s", "merge_recommendation": "approve"})
    await _turn(env, "u-arch", SECURITY)
    assert "Only a Security Engineer or a Project Admin" in await sec.scan_migrated_module.ainvoke({"module_id": "M-01"})
    await _turn(env, "u-arch", REVIEW)
    set_orchestrator_run(True)
    assert "submitted on the Migration Review page" in await rv.submit_migration_review.ainvoke(
        {"module_id": "M-01", "summary": "s", "merge_recommendation": "approve"})


async def test_nothing_is_reviewed_before_the_migration_is_accepted(review_env):
    env = review_env
    await _plan_and_design(env, design_payload=L.design())
    await _paper_baseline(env)
    await _turn(env, "u-arch", REVIEW)
    assert "has no migration record" in await rv.TOOLS[1].ainvoke({"module_id": "M-01"})
