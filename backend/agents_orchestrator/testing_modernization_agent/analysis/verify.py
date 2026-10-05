"""Verify mode (Phase J): the migrated system's two runs against the ACCEPTED baseline, per criterion. Pure.

WHAT IS COMPARED. For each criterion, the scenarios the baseline mapped to it; the baseline's run 1 is the
reference, compared field by field (`noise.compare`) with each of the target's two runs, after ONLY the
criterion's own normalization rules (J4). Nothing else is ignored: the legacy's noise floor is not a licence
to differ — a field the legacy itself varies in, with no rule, is a gap in the plan.

EVERY REMAINING FIELD IS CLASSIFIED BY THE TOOL, not by the model:
  normalization_gap  the legacy varies in it too (the baseline's noise floor) — a rule proposal for
                     Migration Strategy; the criterion stays open until the plan is revised;
  environment        it differs in ONE of the target's two runs but not the other — a sandbox or timing
                     effect, not the code; the criterion stays open (rerun);
  regression         it differs in both runs where the legacy is stable — the criterion fails.
The agent may only re-classify a regression as `accepted_change`, citing an ADR on the module (`apply_accepted`).

VERDICTS ARE COMPUTED (J5): passed (compared, nothing left), failed (a regression), open (a gap or an
environment difference), not_run (no scenario recorded it, or a performance criterion not measured).

PERFORMANCE (J6): p95 on both sides under the same load; the threshold is read from the criterion ("p95 ≤
250 ms"); not measured is `not_run`, never 0.

Masked shapes only (the baseline's rule): no recorded value is in anything this returns.
"""
from __future__ import annotations

import math
import pathlib
import re
from typing import Iterable, Optional

from agents_orchestrator.testing_modernization_agent.analysis.noise import compare as field_diff
from agents_orchestrator.testing_modernization_agent.analysis.noise import covers

_MS = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s)\b", re.IGNORECASE)


def threshold_ms(threshold: Optional[str]) -> Optional[float]:
    """"p95 ≤ 250 ms" → 250.0; "p95 <= 0.5 s" → 500.0; None when it names no time."""
    m = _MS.search(threshold or "")
    if not m:
        return None
    value = float(m.group(1))
    return value * 1000 if m.group(2).lower() == "s" else value


def p95(samples: Iterable[float]) -> Optional[float]:
    """Nearest-rank 95th percentile; None for no samples."""
    xs = sorted(float(x) for x in samples)
    if not xs:
        return None
    return round(xs[max(0, math.ceil(0.95 * len(xs)) - 1)], 1)


def _likely_area(criterion: dict, design: dict) -> Optional[str]:
    """Where in the code a difference most likely comes from: the trap or contract the criterion protects."""
    traps = {t["id"]: t for t in design.get("traps") or []}
    contracts = {c["id"]: c for c in design.get("frozen_contracts") or []}
    for ref in criterion.get("protects") or []:
        if ref in traps:
            return f"{ref}: {traps[ref].get('where') or traps[ref].get('change') or ''}".strip(": ")
    for ref in criterion.get("protects") or []:
        if ref in contracts:
            return f"{ref}: {contracts[ref].get('legacy_location') or contracts[ref].get('name') or ''}".strip(": ")
    return None


def classify(first: dict, second: dict, noise_floor: Iterable[str], rules: list[dict]) -> dict[str, dict]:
    """{field: {classification, cases, example}} for one scenario. `first`/`second` are `noise.compare`
    entries (baseline run 1 vs target run 1 / run 2)."""
    floor = set(noise_floor)
    fields = sorted(set(first.get("varying") or {}) | set(second.get("varying") or {}))
    out = {}
    for f in fields:
        if any(covers(str(r.get("field") or ""), f) for r in rules):
            continue
        in1, in2 = f in (first.get("varying") or {}), f in (second.get("varying") or {})
        kind = "normalization_gap" if f in floor else ("environment" if in1 != in2 else "regression")
        ex = (first.get("examples") or {}).get(f) or (second.get("examples") or {}).get(f) or ["?", "?"]
        out[f] = {"classification": kind, "example": f"{ex[0]} vs {ex[1]}",
                  "cases": max((first.get("varying") or {}).get(f, 0), (second.get("varying") or {}).get(f, 0))}
    return out


def compare_runs(baseline_run1: pathlib.Path, target_run1: pathlib.Path, target_run2: pathlib.Path,
                 scenarios: list[dict]) -> dict[str, tuple[dict, dict]]:
    """{scenario: (baseline vs target run 1, baseline vs target run 2)} — reads files, returns shapes."""
    a = field_diff(baseline_run1, target_run1, scenarios)
    b = field_diff(baseline_run1, target_run2, scenarios)
    return {sc["id"]: (a[sc["id"]], b[sc["id"]]) for sc in scenarios}


def evaluate(*, criteria: list[dict], mapping: dict[str, list[str]], diffs: dict[str, tuple[dict, dict]],
             noise: dict[str, list[str]], design: dict, perf: Optional[dict[str, dict]] = None) -> dict:
    """The verification, from the tools' facts: {criteria: [CriterionResult], differences: [Difference],
    performance: [Performance], rule_proposals: [RuleProposal]} (packet shapes)."""
    perf = perf or {}
    results, differences, performance, proposals = [], [], [], []
    n = 0
    for c in criteria:
        ec = c["id"]
        if c.get("comparison") == "percentile_threshold":
            limit = threshold_ms(c.get("threshold"))
            measured = perf.get(ec) or {}
            legacy, target = measured.get("legacy_p95_ms"), measured.get("target_p95_ms")
            if limit is not None:
                performance.append({"ec_id": ec, "legacy_p95_ms": legacy, "target_p95_ms": target, "threshold_ms": limit})
            if limit is None or legacy is None or target is None:
                results.append({"ec_id": ec, "verdict": "not_run", "cases_compared": None, "normalization_applied": []})
            else:
                results.append({"ec_id": ec, "verdict": "passed" if target <= limit else "failed",
                                "cases_compared": int(measured.get("samples") or 0) or None,
                                "normalization_applied": []})
            continue
        scenarios = [s for s in mapping.get(ec) or [] if s in diffs]  # none recorded it: 0 cases, not run
        rules = list(c.get("normalization") or [])
        cases, kinds = 0, set()
        for sid in scenarios:
            first, second = diffs[sid]
            cases += int(first.get("cases") or 0)
            for fld, d in classify(first, second, noise.get(sid) or [], rules).items():
                n += 1
                kinds.add(d["classification"])
                differences.append({"id": f"EQ-{n:03d}", "ec_id": ec, "classification": d["classification"],
                                    "field": f"{sid}:{fld}", "cases": max(1, d["cases"]),
                                    "masked_example": d["example"], "likely_area": _likely_area(c, design),
                                    "adr_id": None})
                if d["classification"] == "normalization_gap":
                    proposals.append({"ec_id": ec, "field": fld, "rule": "ignore",
                                      "evidence": f"the legacy's own two runs differ in {fld} ({sid}); the target does too"})
        results.append({"ec_id": ec, "verdict": verdict_for(kinds, cases),
                        "cases_compared": cases or None,
                        "normalization_applied": [r.get("field") for r in rules if r.get("field")]})
    return {"criteria": results, "differences": differences, "performance": performance, "rule_proposals": proposals}


def verdict_for(kinds: set[str], cases: int) -> str:
    if not cases:
        return "not_run"
    if "regression" in kinds:
        return "failed"
    if kinds & {"normalization_gap", "environment"}:
        return "open"
    return "passed"


def apply_accepted(result: dict, accepted: dict[str, str], module_adrs: Iterable[str]) -> list[str]:
    """Re-classify regressions as accepted changes, each citing an ADR ON THE MODULE ({EQ-xxx: ADR-yy}), and
    recompute the affected criteria. Returns problems in words (nothing is changed for a refused one)."""
    adrs = set(module_adrs)
    problems = []
    by_id = {d["id"]: d for d in result["differences"]}
    for did, adr in sorted((accepted or {}).items()):
        d = by_id.get(did)
        if d is None:
            problems.append(f"{did} is not a difference of this verification.")
        elif d["classification"] != "regression":
            problems.append(f"{did} is a {d['classification'].replace('_', ' ')}, not a regression: only a regression can "
                            "be an accepted change.")
        elif adr not in adrs:
            problems.append(f"{did} cites {adr}, which is not an ADR on this module in the approved design.")
        else:
            d["classification"], d["adr_id"] = "accepted_change", adr
    for r in result["criteria"]:
        kinds = {d["classification"] for d in result["differences"] if d["ec_id"] == r["ec_id"]}
        if r["verdict"] in ("passed", "failed", "open") and any(d["ec_id"] == r["ec_id"] for d in result["differences"]):
            r["verdict"] = verdict_for(kinds - {"accepted_change"}, r["cases_compared"] or 0)
    return problems


def module_verdict(criteria: list[dict]) -> str:
    verdicts = {c["verdict"] for c in criteria}
    if "failed" in verdicts:
        return "migrating"
    if verdicts == {"passed"}:
        return "verified"
    return "open"
