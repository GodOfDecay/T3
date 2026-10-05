"""Regenerate the `assessment` entry of frontend/components/modernization/__tests__/fixtures.json
from the REAL backend (`assess_repository` on the discovery test repository), keeping the same
inputs (as_of, repository, target stack, scanner result). The view tests promise they render what
the backend produces; hand-editing this file breaks that promise.

    cd backend && uv run python ../help/Track-3/tools/regen_view_fixtures.py
"""
import json
import pathlib
import sys
import tempfile
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

from agents_orchestrator.discovery_agent.analysis.assessment import assess_repository  # noqa: E402
from tests.discovery.legacy_fixture import build_legacy_repo  # noqa: E402

FIXTURES = BACKEND.parent / "frontend" / "components" / "modernization" / "__tests__" / "fixtures.json"
data = json.loads(FIXTURES.read_text(encoding="utf-8"))
old = data["assessment"]
with tempfile.TemporaryDirectory() as tmp:
    root = build_legacy_repo(pathlib.Path(tmp) / "billing")
    # The same scanner input as before: the findings the old fixture recorded, in Trivy's shape.
    # `target` is the file Trivy scanned, kept from the old fixture's own per-dependency findings.
    target_of = {(m["name"], (v.get("package") or "").lower()): v.get("target")
                 for m in old.get("modules") or [] for d in m.get("dependencies") or []
                 for v in d.get("vulnerabilities") or []}
    findings = [{"package": v.get("package"), "installed_version": v.get("version"), "cve": v.get("cve"),
                 "severity": v.get("severity"), "fixed_version": v.get("fixed_version"), "title": v.get("title"),
                 "target": target_of.get((v.get("module"), (v.get("package") or "").lower()))}
                for v in (old.get("flags") or {}).get("vulnerable") or []]
    new = assess_repository(root, as_of=date.fromisoformat(old["as_of"]), repository=old["repository"],
                            target_stack=old["target_stack"], scanners=old.get("scanners"),
                            vulnerabilities=findings)
new["generated_at"] = old["generated_at"]  # stable across regenerations
data["assessment"] = new

# Phase E: the ClaimTrack target design as `record_target_design` stores it (TargetDesignArtifact),
# checked by the same rules against the ClaimTrack fixture repository, and that repository's
# interface inventory as the interfaces route returns it.
from agents_orchestrator.design_modernization_agent.analysis.interfaces import (  # noqa: E402
    capture_interfaces, files_with_interfaces,
)
from agents_orchestrator.design_modernization_agent.tools.design_tools import _tree, check_design  # noqa: E402
from agents_orchestrator.modernization_common.handover.packets import DesignPayload  # noqa: E402
from shared.models.artifacts import TargetDesignArtifact  # noqa: E402
from tests.design_modernization.claimtrack import build_repo, design_payload, fixture  # noqa: E402

brief, assessment = fixture("brief")["payload"], fixture("assessment")["payload"]
modules = [{"id": m["id"], "name": m["name"], "path": m["path"]} for m in assessment["modules"]]
with tempfile.TemporaryDirectory() as tmp:
    repo = build_repo(pathlib.Path(tmp) / "claimtrack")
    inventory = capture_interfaces(repo, modules, assessment["commit"])
    files, dirs = _tree(repo)
    design = DesignPayload.model_validate(design_payload())
    problems, notes = check_design(design, brief, assessment, 1, files, dirs, files_with_interfaces(inventory),
                                   date(2026, 9, 29))
assert not problems, problems
data["target_design"] = TargetDesignArtifact(
    **design.model_dump(mode="json"), system_name=brief["system_name"],
    sources={"brief": {"version": 1, "status": "published"},
             "assessment": {"version": 1, "status": "published", "commit": assessment["commit"],
                            "repository": assessment["repository"]},
             "checkout_commit": assessment["commit"]},
    module_paths={m["id"]: m["path"] for m in modules},
    interfaces={"commit": inventory["commit"], "counts": inventory["counts"], "total": inventory["total"]},
    notes=notes, recorded_at="2026-10-05T10:00:00+00:00",
).model_dump(mode="json")
data["legacy_interfaces"] = {"projectId": "p-claimtrack", "status": "ready", "repository": "claimtrack",
                             "inventory": inventory}

# Phase F: both plans (ClaimTrack and the unrelated Payroll scenario) as `record_migration_strategy`
# stores them — checked by the same rules, built by the same builder.
from agents_orchestrator.modernization_common.handover.packets import PlanPayload  # noqa: E402
from agents_orchestrator.strategy_agent.tools.strategy_tools import build_artifact, check_plan  # noqa: E402
from tests.strategy.scenarios import claimtrack, payroll  # noqa: E402

for key, scenario in (("migration_plan", claimtrack), ("migration_plan_payroll", payroll)):
    b, a, d, p = scenario()
    plan_data = PlanPayload.model_validate(p).model_dump(mode="json", by_alias=True)
    problems, computed = check_plan(plan_data, b, a, d)
    assert not problems, (key, problems)
    data[key] = build_artifact(
        plan_data, b, a, d, computed,
        sources={"brief": {"version": 1, "status": "published"}, "assessment": {"version": 1, "status": "published"},
                 "design": {"version": 1, "status": "published"}},
        notes=[], recorded_at="2026-10-07T10:00:00+00:00")
# Phase G: ClaimTrack Lite's baseline as `record_baseline` stores it — the noise is the MEASURED one
# (tests/testing_modernization/test_sandbox.py asserts a real capture reproduces `lite.NOISE`), built by
# the record tool's own builder; and the captures listing the page polls, in each of its three states.
from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import build_artifact as build_baseline  # noqa: E402
from tests.testing_modernization import lite  # noqa: E402

_manifest = {"id": "cap-20261201090000-a1b2c3", "startedAt": "2026-12-01T09:00:00+00:00",
             "finishedAt": "2026-12-01T09:00:12+00:00", "imageId": "sha256:" + "c9" * 32, "commit": "4f1c2e9a7b" * 4,
             "profileSource": "sdlc-sandbox.json in the legacy code", "requestedBy": "u-qa", "runs": 2,
             "mapping": lite.MAPPING, "notCaptured": lite.NOT_CAPTURED, "noise": lite.NOISE, "stubs": ["fraudscore"],
             "scenarios": [{"id": "claims-read", "kind": "http", "cases": 5, "describes": "Read five claims"},
                           {"id": "settle", "kind": "http", "cases": 6, "describes": "Settle six claims"},
                           {"id": "bank-file", "kind": "batch", "cases": 1, "describes": "The nightly bank file"}]}
data["baseline"] = build_baseline(
    lite.plan(), _manifest, lite.PROPOSALS,
    hash_of=lambda scs: __import__("hashlib").sha256("|".join(sorted(scs)).encode()).hexdigest(), region="local-dev",
    sources={"plan": {"version": 1, "status": "published"}, "design": {"version": 1, "status": "published"}},
    system_name="ClaimTrack Lite",
    notes=["Captured from commit 4f1c2e9a7b with sdlc-sandbox.json in the legacy code; data: synthetic.",
           "2 normalization rule(s) proposed to Migration Strategy — the criteria they belong to stay open until the "
           "plan is revised."],
    recorded_at="2026-12-01T09:05:00+00:00")
_keys = ("id", "status", "startedAt", "finishedAt", "error", "planVersion", "commit", "mapping", "scenarios", "keep")
data["captures"] = {"projectId": "p-claimtrack", "captures": [
    {"id": "cap-20261201100000-d4e5f6", "status": "running", "startedAt": "2026-12-01T10:00:00+00:00",
     "finishedAt": None, "error": None, "planVersion": 1, "commit": _manifest["commit"], "mapping": lite.MAPPING,
     "scenarios": _manifest["scenarios"], "keep": False},
    {"id": "cap-20261201093000-0a0b0c", "status": "failed", "startedAt": "2026-12-01T09:30:00+00:00",
     "finishedAt": "2026-12-01T09:31:02+00:00",
     "error": "The legacy service did not answer on /health within 60 seconds; its container is exited (exit 3).",
     "planVersion": 1, "commit": _manifest["commit"], "mapping": lite.MAPPING, "scenarios": _manifest["scenarios"],
     "keep": False},
    {**{k: _manifest.get(k) for k in _keys}, "status": "complete", "planVersion": 1, "error": None, "keep": True},
]}
# Phase H: ClaimTrack Lite's claims API migrated (M-01), as `record_module_migration` stores it — built by the
# record tool's own builder. The previews are what tests/development_modernization/test_chain.py MEASURED on the
# real sandbox: identical after normalization once both traps are handled; the two half-cent payouts when the
# rounding trap (TR-01) is left in. And the workspaces listing the page shows.
from agents_orchestrator.development_modernization_agent.tools.migration_tools import build_artifact as build_migration  # noqa: E402
from tests.development_modernization.lite_h import design as lite_design  # noqa: E402

_item = {"legacy_path": "claims-api", "name": "claims-api", "tier": "llm_assisted", "patterns": ["in_place_upgrade"],
         "wave": "W1", "baseline_ids": ["BL-01", "BL-02"], "trap_ids": ["TR-01", "TR-02"],
         "target_runtime": "Java 21 · Node 24 · Python 3.12", "legacy_runtime": "Python 2.7", "ecosystem": "python"}
_shas = ["9a1f0c2b3d" * 4, "8b2e1d3c4f" * 4, "7c3d2e4f5a" * 4, "6d4e3f5a6b" * 4, "5e5f4a6b7c" * 4, "4f6a5b7c8d" * 4]
_commits = [{"sha": _shas[0], "subject": "Start main for the migration"},
            {"sha": _shas[1], "subject": "copy: Copy claims-api from the legacy code at 4f1c2e9a7b, unchanged"},
            {"sha": _shas[2], "subject": "recipe: lib2to3 CPython 3.12.14 stdlib over claims-api"},
            {"sha": _shas[3], "subject": "build: run on Python 3.12 (pinned)"},
            {"sha": _shas[4], "subject": "fix: TR-02 bytes on the socket"},
            {"sha": _shas[5], "subject": "fix: TR-01 legacy rounding kept"}]
_clean = {"claims-read": {"cases": 5, "differences": {}, "examples": {}, "ignored": ["generatedAt", "requestId"]},
          "settle": {"cases": 6, "differences": {}, "examples": {}, "ignored": ["requestId", "settledAt"]}}
_rounding = {"claims-read": _clean["claims-read"],
             "settle": {"cases": 6, "differences": {"payout": 2}, "examples": {"payout": ["<number>", "<number>"]},
                        "ignored": ["requestId", "settledAt"]}}
_state = {"branch": "migrate/claims-api", "base_branch": "main", "base_sha": _shas[0], "legacy_commit": "4f1c2e9a7b" * 4,
          "recipes": [{"tool": "lib2to3", "version": "CPython 3.12.14 stdlib (image 6d462c84e51f)",
                       "args": "-W ignore -m lib2to3 -w -n --no-diffs claims-api"}],
          "builds": [{"ok": False, "failing": "claims-api/server.py:8: cannot import BaseHTTPServer on this runtime", "head": _shas[1]},
                     {"ok": True, "head": _shas[2]}, {"ok": True, "head": _shas[3]}, {"ok": True, "head": _shas[4]},
                     {"ok": True, "head": _shas[5]}],
          "tests": {"status": "not_run", "head": _shas[5], "note": "the module has no tests"},
          "lint": {"status": "green", "head": _shas[5]},
          "preview": {"head": _shas[5], "baseline_version": 1, "scenarios": _clean,
                      "headline": "11 case(s) identical to the baseline after normalization"}}
_sources = {"design": {"version": 1, "status": "published"}, "plan": {"version": 1, "status": "published"},
            "baseline": {"version": 1, "status": "published"}}
_files = ["claims-api/requirements.txt", "claims-api/runtime.txt", "claims-api/server.py"]
data["migration"] = build_migration(
    module_id="M-01", outcome="ready_for_review", item=_item, state=_state,
    file_map=[{"legacy_path": f, "disposition": "mapped", "target_path": f} for f in _files],
    rewritten=[{"file": "claims-api/server.py", "reason": "legacy rounding kept (TR-01); bytes on the socket (TR-02)"}],
    traps_handled={"TR-01": "claims-api/server.py payout(): Decimal ROUND_HALF_UP on the exact value",
                   "TR-02": "claims-api/server.py Handler.reply(): the JSON is encoded to bytes before the socket write"},
    vault_references=[], follow_ups=["settlement-batch (M-02) still runs Python 2 code: the shared image moves with it in W2"],
    handoff_note=None, commits=_commits, changed=["Dockerfile", *_files], head=_shas[5], sources=_sources,
    system_name=lite_design()["system_name"], notes=["Legacy code at 4f1c2e9a7b; target branch from main."],
    recorded_at="2026-12-02T11:00:00+00:00")
_failed_state = {**_state, "builds": [{"ok": False, "failing": "claims-api/server.py:8: cannot import BaseHTTPServer on this runtime\n"
                                                              "claims-api/server.py:14: cannot import urllib2 on this runtime",
                                       "head": _shas[1]}] * 5,
                 "preview": {"head": _shas[1], "baseline_version": 1, "scenarios": _rounding,
                             "headline": "1 field(s) differ from the baseline in 11 case(s)"}}
data["migration_failed"] = build_migration(
    module_id="M-01", outcome="build_failed", item=_item, state=_failed_state,
    file_map=[{"legacy_path": f, "disposition": "mapped", "target_path": f} for f in _files], rewritten=[],
    traps_handled={}, vault_references=["kv://claimtrack/fraud-api-key"],
    follow_ups=["The build is still red after five rounds: the HTTP server needs a person to port"],
    handoff_note=None, commits=_commits[:2], changed=_files, head=_shas[1], sources=_sources, system_name="ClaimTrack Lite",
    notes=[], recorded_at="2026-12-02T09:00:00+00:00")
data["migration_rounding"] = {**data["migration"], "preview": {**data["migration"]["preview"], "scenarios": _rounding,
                              "headline": "1 field(s) differ from the baseline in 11 case(s)"}}
data["migration_blocked"] = build_migration(
    module_id="M-02", outcome="blocked", item={**_item, "legacy_path": "settlement-batch", "name": "settlement-batch",
                                                "tier": "manual", "trap_ids": ["TR-01"]},
    state=None, file_map=[], rewritten=[], traps_handled={}, vault_references=[], follow_ups=[],
    handoff_note="The bank file format is owned by the bank's spec v7; a person must redesign the writer.",
    commits=[], changed=[], head=None, sources=_sources, system_name="ClaimTrack Lite", notes=[],
    recorded_at="2026-12-02T12:00:00+00:00")
data["migration_workspaces"] = {"projectId": "p-claimtrack", "workspaces": [
    {"moduleId": "M-01", "modulePath": "claims-api", "branch": "migrate/claims-api", "baseBranch": "main",
     "ecosystem": "python", "targetRuntime": _item["target_runtime"],
     "commits": [{"sha": c["sha"][:10], "concern": c["subject"].split(":")[0], "message": c["subject"].split(": ", 1)[-1],
                  "files": 1} for c in _commits[1:]],
     "recipes": [{"tool": "lib2to3", "version": _state["recipes"][0]["version"], "files": 1}],
     "builds": [{"round": n, "ok": b["ok"], "at": "2026-12-02T10:0%d:00+00:00" % n} for n, b in enumerate(_state["builds"], 1)],
     "tests": "not_run", "lint": "green", "preview": _state["preview"]["headline"],
     "pushed": {"head": _shas[5], "at": "2026-12-02T11:30:00+00:00", "pr_url": "https://github.com/claimtrack/claimtrack-lite-target/pull/1"},
     "openedAt": "2026-12-02T10:00:00+00:00"},
]}
# Phase I: the review and the security report of that migration, built by the submit tools' own builders. The
# API diff and the anti-pattern scan are COMPUTED here by the review's analysis on the sample and the migrated
# server (tests/review_security_modernization/lite_i.py) — the faithful one and the broken one (rounding trap
# left in, 409 → 400, /metrics added) — not typed in.
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402

from agents_orchestrator.code_review_modernization_agent.tools.review_tools import build_artifact as build_review, compute  # noqa: E402
from agents_orchestrator.modernization_common.review_checkout import Migration as _Mig  # noqa: E402
from agents_orchestrator.security_modernization_agent.tools.security_tools import build_artifact as build_security  # noqa: E402
from tests.review_security_modernization import lite_i  # noqa: E402

_ldesign = lite_i.design()
_ctx = {"name": "claims-api", "tier": "llm_assisted", "patterns": ["in_place_upgrade"],
        "contracts": [c for c in _ldesign["frozen_contracts"] if c["id"] == "CT-01"],
        "traps": [t for t in _ldesign["traps"] if "M-01" in t["affects"]],
        "criteria": [{"id": e} for e in ("EC-01", "EC-02", "EC-04")], "waves": [{"id": "W1", "starts": "2026-12-01", "ends": "2027-01-31"}],
        "system_name": "ClaimTrack Lite", "sources": {k: v for k, v in _sources.items() if k != "baseline"}}


def _mig(server_text: str, version: int, head: str) -> _Mig:
    tmp = pathlib.Path(_tempfile.mkdtemp())
    _shutil.copytree(lite.SAMPLE / "claims-api", tmp / "claims-api")
    (tmp / "claims-api" / "server.py").write_text(server_text, encoding="utf-8")
    return _Mig(module_id="M-01", record={**data["migration"], "pr_url": "https://github.com/claimtrack/claimtrack-lite-target/pull/1"},
                version=version, status="published", head=head, branch="migrate/claims-api", module_path="claims-api",
                ledger={"state": "in_review", "wave": "W1"}, target=tmp, legacy=lite.SAMPLE, legacy_commit="4f1c2e9a7b" * 4)


_good, _bad = _mig(lite_i.migrated_server(), 1, _shas[5]), _mig(lite_i.broken_server(), 2, "3a7b6c8d9e" * 4)
_files_read = {"target": ["claims-api/server.py"], "legacy": ["claims-api/server.py"]}
_checks = {
    "contract_check": [{"ct_id": "CT-01", "status": "unchanged",
                        "note": "The same JSON on every route; encoded to bytes for the socket (TR-02)."}],
    "trap_check": [{"tr_id": "TR-01", "status": "handled", "where": "claims-api/server.py:28"},
                   {"tr_id": "TR-02", "status": "handled", "where": "claims-api/server.py:53"}],
    "equivalence_coverage": [{"ec_id": e, "status": "covered", "note": ""} for e in ("EC-01", "EC-02", "EC-04")],
    "traceability": [{"legacy_path": f, "target_path": f, "status": "mapped"} for f in _files]}
_diff, _hits = compute(_good, _ctx)
data["review"] = build_review(module_id="M-01", mig=_good, ctx=_ctx, opened=_files_read, diff=_diff, hits=_hits,
                              recorded_at="2026-12-03T10:00:00+00:00", review={
    "summary": "A faithful port: both traps handled where the design says, every route, status code and SQL statement kept.",
    "merge_recommendation": "approve", "findings": [],
    "known_debt": [{"pattern": "Hard-coded host", "legacy_file": "claims-api/server.py", "note": "FRAUD_URL default; the environment overrides it"}],
    **_checks})
_bdiff, _bhits = compute(_bad, _ctx)
data["review_changes"] = build_review(module_id="M-01", mig=_bad, ctx=_ctx, opened=_files_read, diff=_bdiff, hits=_bhits,
                                      recorded_at="2026-12-03T11:00:00+00:00", review={
    "summary": "The rounding trap is not handled and a settled claim answers 400 instead of 409.",
    "merge_recommendation": "request_changes",
    "findings": [
        {"id": "F-001", "severity": "high", "category": "trap_unhandled", "file": "claims-api/server.py", "line": 27,
         "legacy_file": "claims-api/server.py", "legacy_line": 27, "refs": ["TR-01", "EC-02"],
         "description": "Python 3 round() rounds halves to even: two half-cent payouts pay a cent less.",
         "recommendation": "Decimal ROUND_HALF_UP on the exact value, as the design's TR-01 says."},
        {"id": "F-002", "severity": "high", "category": "contract_drift", "file": "claims-api/server.py", "line": 84,
         "legacy_file": "claims-api/server.py", "legacy_line": 82, "refs": ["CT-01"],
         "description": "Settling a claim that is not open answers 400; the legacy answers 409.", "recommendation": "Answer 409."},
        {"id": "F-003", "severity": "medium", "category": "scope_creep", "file": "claims-api/server.py", "line": 60,
         "description": "A /metrics route was added; no ADR asks for it.", "recommendation": "Remove it from this migration."}],
    **{**_checks, "contract_check": [{"ct_id": "CT-01", "status": "changed", "note": "409 → 400; /metrics added"}],
       "trap_check": [{"tr_id": "TR-01", "status": "not_handled", "where": ""}, _checks["trap_check"][1]]}})
# Security: the scanners' results as the chain test measured them on the sample (Semgrep's bind-all on both
# sides; Trivy and Gitleaks clean), plus a variant where Gitleaks did not run.
_bind = {"tool": "semgrep", "rule": "py-bind-all", "title": "Server binds every interface", "severity": "low",
         "file": "claims-api/server.py", "line": 99, "package": None, "version": None, "cve": None, "fixed_version": None,
         "secret_hash": None}
_py2 = {**_bind, "rule": "py-eval-exec", "title": "eval or exec of a value", "severity": "high", "line": 12}
_state_sec = {"target": {"scans": {"trivy": "ran", "semgrep": "ran", "gitleaks": "ran"}, "notes": {},
                         "findings": [_bind], "sbom": {"components": 0, "vulnerabilities": 0},
                         "versions": {"trivy": "0.58.1", "semgrep": "1.99.0", "gitleaks": "8.21.2"}},
              "carryover": [], "authz": {"CT-01": {"suggested": "same", "reason": "no authentication marker on either side",
                                                   "legacy": {}, "target": {}, "legacy_file": "claims-api/server.py",
                                                   "target_files": ["claims-api/server.py"], "found": True}}}
_legacy_sec = {"findings": [{**_bind, "line": 98}, _py2], "served_from_cache": True}
_sdiff = {"target": [{**_bind, "origin": "carried_over", "legacy_ref": "claims-api/server.py:98"}],
          "fixed": [{**_py2, "origin": "fixed", "legacy_ref": "claims-api/server.py:12"}]}
data["security"] = build_security(module_id="M-01", mig=_good, ctx=_ctx, state=_state_sec, legacy=_legacy_sec, diff=_sdiff,
                                  recorded_at="2026-12-03T12:00:00+00:00", report={
    "verdict": "CONDITIONAL", "rationale": "Nothing introduced. One low finding carried over (the server binds every interface), "
                                           "with a plan inside the wave.",
    "findings": [{"id": "S-001", "title": "Server binds every interface", "severity": "low", "origin": "carried_over",
                  "legacy_ref": "claims-api/server.py:98", "reachable": True, "file": "claims-api/server.py",
                  "remediation_plan": "Bind to the container interface from configuration", "remediation_due": "2027-01-15"}],
    "contract_authz": [{"ct_id": "CT-01", "status": "same", "note": "No authentication on either side, as before (gateway-enforced)."}]})
_state_partial = {**_state_sec, "target": {**_state_sec["target"], "scans": {"trivy": "not_installed", "semgrep": "ran", "gitleaks": "ran"},
                                           "notes": {"trivy": "Trivy's vulnerability database is not on this server."},
                                           "sbom": {"components": None, "vulnerabilities": None}}}
data["security_unscanned"] = build_security(module_id="M-01", mig=_good, ctx=_ctx, state=_state_partial, legacy={"findings": []},
                                            diff={"target": [], "fixed": []}, recorded_at="2026-12-03T12:30:00+00:00", report={
    "verdict": "FAIL", "rationale": "Dependencies were not scanned; the sign-off waits for the database.", "findings": [],
    "contract_authz": [{"ct_id": "CT-01", "status": "same", "note": ""}]})
FIXTURES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"assessment: schema {new['schema_version']}, {len(new['modules'])} modules, "
      f"{len(new['not_assessable_statically'])} not-assessable questions")
print(f"target_design: {len(design.modules)} modules, {len(notes)} notes; interfaces: {inventory['total']}")
