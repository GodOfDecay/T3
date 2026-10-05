"""Writes the Phase J mutation specs (R46): Equivalence Testing Verify mode, and the workflow fixes before it.

    python help/Track-3/tools/specs-phase-j/make_specs.py
    cd backend && for s in ../help/Track-3/tools/specs-phase-j/spec_j_*.json; do .venv/bin/python ../help/Track-3/tools/mutate.py $s; done
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
V = "agents_orchestrator/testing_modernization_agent/analysis/verify.py"

SPECS = {
    "spec_j_verify.json": {
        "target": V, "tests": ["tests/testing_modernization/test_verify_units.py"],
        "mutants": [
            ["rules-ignored", '        if any(covers(str(r.get("field") or ""), f) for r in rules):\n            continue', "        pass"],
            ["gap-is-regression", '        kind = "normalization_gap" if f in floor else ("environment" if in1 != in2 else "regression")',
             '        kind = "environment" if in1 != in2 else "regression"'],
            ["env-is-regression", '        kind = "normalization_gap" if f in floor else ("environment" if in1 != in2 else "regression")',
             '        kind = "normalization_gap" if f in floor else "regression"'],
            ["one-run-only", "    fields = sorted(set(first.get(\"varying\") or {}) | set(second.get(\"varying\") or {}))",
             "    fields = sorted(set(first.get(\"varying\") or {}))"],
            ["regression-passes", '    if "regression" in kinds:\n        return "failed"', '    if False:\n        return "failed"'],
            ["gap-passes", '    if kinds & {"normalization_gap", "environment"}:\n        return "open"', '    if False:\n        return "open"'],
            ["nothing-compared-passes", "    if not cases:\n        return \"not_run\"", "    if False:\n        return \"not_run\""],
            ["unmeasured-passes", "            if limit is None or legacy is None or target is None:", "            if limit is None:"],
            ["slow-passes", '"passed" if target <= limit else "failed"', '"passed"'],
            ["seconds-as-ms", '    return value * 1000 if m.group(2).lower() == "s" else value', "    return value"],
            ["p95-is-max", "    return round(xs[max(0, math.ceil(0.95 * len(xs)) - 1)], 1)", "    return round(xs[-1], 1)"],
            ["any-adr", "        elif adr not in adrs:", "        elif False:"],
            ["accept-a-gap", '        elif d["classification"] != "regression":', "        elif False:"],
            ["accepted-not-recomputed", '            r["verdict"] = verdict_for(kinds - {"accepted_change"}, r["cases_compared"] or 0)', "            pass"],
            ["no-proposals", '                if d["classification"] == "normalization_gap":\n                    proposals.append', '                if False:\n                    proposals.append'],
            ["open-is-verified", '    if verdicts == {"passed"}:\n        return "verified"', '    if "failed" not in verdicts:\n        return "verified"'],
            ["no-likely-area", '                                    "masked_example": d["example"], "likely_area": _likely_area(c, design),',
             '                                    "masked_example": d["example"], "likely_area": None,'],
        ],
    },
    "spec_j_rework.json": {
        "target": "agents_orchestrator/development_modernization_agent/tools/migration_tools.py",
        "tests": ["tests/development_modernization/test_units.py"],
        "mutants": [
            ["unhandled-trap-hidden", '            if t.get("status") == "not_handled":', "            if False:"],
            ["carryover-hidden", '        for c in sp.get("secret_carryover") or []:', "        for c in []:"],
            ["weaker-hidden", '            if a.get("status") == "weaker":', "            if False:"],
            ["unsorted", '        for f in sorted(r.get("findings") or [], key=lambda f: (sev.get(f.get("severity"), 9), f.get("id") or "")):',
             '        for f in r.get("findings") or []:'],
        ],
    },
    "spec_j_per_subject.json": {
        "target": "shared/services/artifact_versions.py", "env_test": True,
        "tests": ["tests/modernization_common/test_per_subject_versions.py"],
        "mutants": [
            ["stage-wide-supersede", "    current = await latest_published(db, project_id, stage, subject=subject_of(stage, row.payload))",
             "    current = await latest_published(db, project_id, stage, subject=None)"],
            ["verify-is-baseline", "        return f\"verify:{p.get('module_id')}\" if p.get(\"mode\") == \"verify\" else \"baseline\"",
             "        return \"baseline\""],
            ["no-default-subject", 'DEFAULT_SUBJECT = {"testing_modernization": "baseline"}', "DEFAULT_SUBJECT = {}"],
            ["all-stages-per-module", "    if stage not in PER_SUBJECT_STAGES:\n        return None", "    if False:\n        return None"],
        ],
    },
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps({"root": "backend", **spec}, indent=1) + "\n", encoding="utf-8")
print(f"{len(SPECS)} specs, {sum(len(s['mutants']) for s in SPECS.values())} mutants")
