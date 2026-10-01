"""From a capture to a baseline — the rules and the builder (Phase G). Pure; no Docker, no database.

  mapping      which scenarios record which equivalence criterion. Every criterion named is the
               plan's, every scenario the profile's. A module is baselined WHOLE: each of its criteria
               (and every criterion for "all" modules) is either mapped or listed as not captured,
               with the reason — a partial baseline must not look complete.
  proposals    every field that varies between the two runs and no normalization rule of that
               criterion covers is PROPOSED to Migration Strategy (field + rule); a proposal for a
               field that did not vary is refused. The evidence is written here from the counts,
               never by the model.
  baselines    one BL-xx per (module, scenario set): its criteria, the case count, run 1's hash,
               the region and the noise fields.
  placements   what approval writes on the ledger: each baselined module and its BL ids.
"""
from __future__ import annotations

from typing import Iterable

from agents_orchestrator.testing_modernization_agent.analysis.noise import covered


def criteria_by_id(plan: dict) -> dict[str, dict]:
    return {c["id"]: c for c in plan.get("equivalence_criteria") or []}


def check_mapping(plan: dict, scenario_ids: Iterable[str], mapping: dict, not_captured: list[dict]) -> list[str]:
    ecs = criteria_by_id(plan)
    scenarios = set(scenario_ids)
    problems: list[str] = []
    if not isinstance(mapping, dict) or not mapping:
        return ["Map at least one equivalence criterion to the scenarios that record it: "
                "{\"EC-01\": [\"claims-read\"], ...}."]
    for ec, scs in mapping.items():
        if ec not in ecs:
            problems.append(f"{ec} is not a criterion of the approved plan.")
            continue
        if not isinstance(scs, list) or not scs:
            problems.append(f"{ec} is mapped to no scenario.")
            continue
        unknown = sorted(set(scs) - scenarios)
        if unknown:
            problems.append(f"{ec} is mapped to {', '.join(unknown)}, which the capture profile does not have.")
    skipped = {}
    for n in not_captured or []:
        ec, reason = (n or {}).get("ec_id"), str((n or {}).get("reason") or "").strip()
        if ec not in ecs:
            problems.append(f"{ec} (not captured) is not a criterion of the approved plan.")
        elif len(reason) < 3:
            problems.append(f"{ec} is listed as not captured without a reason; say why (for example a load "
                            "test, which Baseline mode does not run).")
        elif ec in mapping:
            problems.append(f"{ec} is both mapped and listed as not captured; choose one.")
        else:
            skipped[ec] = reason
    touched = {ecs[ec]["module_id"] for ec in mapping if ec in ecs} - {"all"}
    for ec, c in sorted(ecs.items()):
        if (c["module_id"] in touched or c["module_id"] == "all") and ec not in mapping and ec not in skipped:
            where = "every module" if c["module_id"] == "all" else c["module_id"]
            problems.append(f"{ec} ({where}) is neither recorded nor listed as not captured. A module is "
                            "baselined whole: map it to a scenario, or say why it cannot be captured.")
    return problems


def varying_for(ec_scenarios: list[str], noise: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for sid in ec_scenarios:
        for fld, count in (noise.get(sid) or {}).get("varying", {}).items():
            out[fld] = out.get(fld, 0) + count
    return out


def uncovered(plan: dict, mapping: dict, noise: dict) -> dict[str, list[str]]:
    """{ec: [varying fields no rule of that criterion covers]} — each needs a proposal."""
    ecs = criteria_by_id(plan)
    out = {}
    for ec, scs in sorted(mapping.items()):
        fields = varying_for(scs, noise)
        rest = sorted(set(fields) - set(covered(fields, ecs[ec].get("normalization") or [])))
        if rest:
            out[ec] = rest
    return out


def check_proposals(plan: dict, mapping: dict, noise: dict, proposals: list[dict]) -> list[str]:
    need = uncovered(plan, mapping, noise)
    problems = []
    given = set()
    for p in proposals or []:
        ec, fld, rule = (p or {}).get("ec_id"), (p or {}).get("field"), str((p or {}).get("rule") or "").strip()
        if ec not in need or fld not in need[ec]:
            problems.append(f"The proposal for {ec} / {fld} is for a field that did not vary between the two "
                            "runs (or a rule already covers it); propose only what the noise report lists.")
        elif not rule:
            problems.append(f"The proposal for {ec} / {fld} gives no rule (for example \"ignore the value, "
                            "require it present\").")
        else:
            given.add((ec, fld))
    for ec, fields in need.items():
        for fld in fields:
            if (ec, fld) not in given:
                problems.append(f"{fld} varies between two runs of the unchanged legacy system for {ec} and no "
                                "rule covers it: propose a normalization rule to Migration Strategy (field, rule) "
                                "— never apply one yourself.")
    return problems


def evidence(ec: str, fld: str, mapping: dict, noise: dict) -> str:
    cases = sum((noise.get(s) or {}).get("cases", 0) for s in mapping[ec])
    count = varying_for(mapping[ec], noise).get(fld, 0)
    shapes = next(((noise.get(s) or {}).get("examples", {}).get(fld) for s in mapping[ec]
                   if fld in (noise.get(s) or {}).get("examples", {})), None)
    shown = f"; run 1 {shapes[0]} vs run 2 {shapes[1]}" if shapes else ""
    return (f"differs between two runs of the unchanged legacy system on identical input in {count} of {cases} "
            f"case(s) ({', '.join(mapping[ec])}){shown}")


def build(plan: dict, mapping: dict, noise: dict, proposals: list[dict], not_captured: list[dict],
          stubs: list[str], hash_of, region: str, captured_at: str) -> dict:
    """The `BaselinePayload` fields. `hash_of(scenario ids) -> sha256`."""
    ecs = criteria_by_id(plan)
    groups: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for ec in sorted(mapping, key=lambda e: (ecs[e]["module_id"], e)):
        groups.setdefault((ecs[ec]["module_id"], tuple(sorted(mapping[ec]))), []).append(ec)
    baselines = []
    for n, ((module, scs), ec_ids) in enumerate(sorted(groups.items(), key=lambda g: (g[0][0], g[1][0])), 1):
        kinds = {(noise.get(s) or {}).get("kind") for s in scs}
        baselines.append({
            "id": f"BL-{n:02d}", "ec_ids": ec_ids, "module_id": module,
            "count": max(1, sum((noise.get(s) or {}).get("cases", 0) for s in scs)),
            "unit": "cases" if "http" in kinds else "runs",
            "sha256": hash_of(list(scs)), "region": region,
            "noise_fields": sorted(varying_for(list(scs), noise)), "captured_at": captured_at,
        })
    reports = []
    for ec in sorted(mapping):
        fields = sorted(varying_for(mapping[ec], noise))
        reports.append({"ec_id": ec, "runs_compared": 2, "varying_fields": fields,
                        "covered_by_rule": covered(fields, ecs[ec].get("normalization") or [])})
    return {
        "mode": "baseline", "baselines": baselines, "noise": reports,
        "rule_proposals": [{"ec_id": p["ec_id"], "field": p["field"], "rule": str(p["rule"]).strip(),
                            "evidence": evidence(p["ec_id"], p["field"], mapping, noise)} for p in proposals or []],
        "stubs": sorted(stubs),
        "not_captured": [{"ec_id": n["ec_id"], "reason": str(n["reason"]).strip()} for n in not_captured or []],
    }


def placements(payload: dict) -> list[dict]:
    """Each baselined module with its BL ids (baselines for "all" modules go to every one of them)."""
    shared = [b["id"] for b in payload["baselines"] if b["module_id"] == "all"]
    modules = sorted({b["module_id"] for b in payload["baselines"]} - {"all"})
    return [{"module_id": m, "baseline_ids": [b["id"] for b in payload["baselines"] if b["module_id"] == m] + shared}
            for m in modules]
