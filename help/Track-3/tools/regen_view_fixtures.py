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
FIXTURES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"assessment: schema {new['schema_version']}, {len(new['modules'])} modules, "
      f"{len(new['not_assessable_statically'])} not-assessable questions")
print(f"target_design: {len(design.modules)} modules, {len(notes)} notes; interfaces: {inventory['total']}")
