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
FIXTURES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"assessment: schema {new['schema_version']}, {len(new['modules'])} modules, "
      f"{len(new['not_assessable_statically'])} not-assessable questions")
