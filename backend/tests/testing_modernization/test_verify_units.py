"""Equivalence Testing, Verify mode (Phase J) — the pure parts: the comparison against the accepted baseline,
the classification the TOOL makes (regression / normalization gap / environment), accepted changes only with
an ADR on the module, computed verdicts, performance both sides (not measured is not run, never 0), and the
packet's rules on the result."""
from __future__ import annotations

import json
import pathlib

import pytest

from agents_orchestrator.modernization_common.handover.packets import EquivalencePayload
from agents_orchestrator.testing_modernization_agent.analysis import verify as V

pytestmark = pytest.mark.unit

DESIGN = {"traps": [{"id": "TR-01", "where": "claims-api/server.py payout()"}],
          "frozen_contracts": [{"id": "CT-01", "legacy_location": "claims-api/server.py:58"}]}
CRITERIA = [
    {"id": "EC-01", "comparison": "exact", "protects": ["CT-01"], "normalization": [{"field": "generatedAt", "rule": "ignore"}]},
    {"id": "EC-02", "comparison": "exact", "protects": ["TR-01"], "normalization": [{"field": "settledAt", "rule": "ignore"}]},
    {"id": "EC-04", "comparison": "percentile_threshold", "threshold": "p95 ≤ 250 ms", "protects": ["CT-01"]},
]
MAPPING = {"EC-01": ["claims-read"], "EC-02": ["settle"]}


def _write(root: pathlib.Path, sid: str, bodies: list[dict]) -> None:
    (root / sid).mkdir(parents=True, exist_ok=True)
    (root / sid / "responses.jsonl").write_text("".join(
        json.dumps({"request": {"method": "GET", "path": "/x"}, "status": 200, "contentType": "application/json",
                    "body": b}, sort_keys=True) + "\n" for b in bodies))


def _runs(tmp_path, *, settle_t1, settle_t2, read_t=None):
    base = [{"payout": 0.13, "settledAt": "2026-01-01T00:00:00Z", "requestId": "a"}]
    read = [{"claim": {"id": "CLM-0001"}, "generatedAt": "2026-01-01T00:00:00Z", "requestId": "a"}]
    for name, settle, rd in (("b", base, read), ("t1", settle_t1, read_t or read), ("t2", settle_t2, read_t or read)):
        _write(tmp_path / name, "settle", settle)
        _write(tmp_path / name, "claims-read", rd)
    scen = [{"id": "settle", "kind": "http"}, {"id": "claims-read", "kind": "http"}]
    return V.compare_runs(tmp_path / "b", tmp_path / "t1", tmp_path / "t2", scen)


def _evaluate(diffs, noise=None, perf=None):
    return V.evaluate(criteria=CRITERIA, mapping=MAPPING, diffs=diffs, noise=noise or {"settle": ["requestId"],
                      "claims-read": ["requestId", "generatedAt"]}, design=DESIGN, perf=perf)


def test_a_faithful_target_passes_and_the_performance_criterion_is_measured_on_both_sides(tmp_path):
    same = [{"payout": 0.13, "settledAt": "2026-02-02T00:00:00Z", "requestId": "z"}]
    diffs = _runs(tmp_path, settle_t1=same, settle_t2=same)
    r = _evaluate(diffs, noise={"settle": [], "claims-read": []}, perf={"EC-04": {"legacy_p95_ms": 12.0, "target_p95_ms": 9.5, "samples": 100}})
    # requestId differs and NO rule covers it, but the legacy did not vary in it here (noise {}): a regression.
    assert {d["field"] for d in r["differences"]} == {"settle:requestId"}
    r = _evaluate(diffs, perf={"EC-04": {"legacy_p95_ms": 12.0, "target_p95_ms": 9.5, "samples": 100}})
    verdicts = {c["ec_id"]: c["verdict"] for c in r["criteria"]}
    assert verdicts == {"EC-01": "passed", "EC-02": "open", "EC-04": "passed"}
    assert {d["classification"] for d in r["differences"]} == {"normalization_gap"}
    assert {p["field"] for p in r["rule_proposals"]} == {"requestId"}
    assert r["performance"] == [{"ec_id": "EC-04", "legacy_p95_ms": 12.0, "target_p95_ms": 9.5, "threshold_ms": 250.0}]


def test_the_rounding_trap_left_in_is_a_regression_on_its_criterion_with_the_likely_area(tmp_path):
    wrong = [{"payout": 0.12, "settledAt": "x", "requestId": "a"}]
    r = _evaluate(_runs(tmp_path, settle_t1=wrong, settle_t2=wrong))
    reg = [d for d in r["differences"] if d["classification"] == "regression"]
    assert [(d["ec_id"], d["field"], d["cases"], d["masked_example"]) for d in reg] == [
        ("EC-02", "settle:payout", 1, "<number> vs <number>")]
    assert reg[0]["likely_area"] == "TR-01: claims-api/server.py payout()"
    assert {c["ec_id"]: c["verdict"] for c in r["criteria"]}["EC-02"] == "failed"
    assert V.module_verdict(r["criteria"]) == "migrating"
    assert "0.12" not in json.dumps(r) and "CLM-0001" not in json.dumps(r)


def test_a_difference_in_one_run_only_is_the_environment(tmp_path):
    base = [{"payout": 0.13, "settledAt": "x", "requestId": "a"}]
    r = _evaluate(_runs(tmp_path, settle_t1=[{**base[0], "payout": 0.12}], settle_t2=base))
    d = next(d for d in r["differences"] if d["field"] == "settle:payout")
    assert d["classification"] == "environment"
    assert {c["ec_id"]: c["verdict"] for c in r["criteria"]}["EC-02"] == "open"


def test_a_difference_only_in_the_second_run_is_seen_too(tmp_path):
    base = [{"payout": 0.13, "settledAt": "x", "requestId": "a"}]
    r = _evaluate(_runs(tmp_path, settle_t1=base, settle_t2=[{**base[0], "payout": 0.12}]))
    assert next(d for d in r["differences"] if d["field"] == "settle:payout")["classification"] == "environment"


def test_a_scenario_with_no_cases_is_not_run():
    assert V.verdict_for(set(), 0) == "not_run" and V.verdict_for(set(), 3) == "passed"
    r = V.evaluate(criteria=[CRITERIA[0]], mapping=MAPPING, diffs={"claims-read": ({"cases": 0}, {"cases": 0})},
                   noise={}, design=DESIGN)
    assert (r["criteria"][0]["verdict"], r["criteria"][0]["cases_compared"]) == ("not_run", None)


def test_only_the_criterions_own_rules_apply(tmp_path):
    # generatedAt is EC-01's rule, not EC-02's: a target that adds it to settle differs there.
    base = [{"payout": 0.13, "settledAt": "x", "requestId": "a"}]
    r = _evaluate(_runs(tmp_path, settle_t1=[{**base[0], "generatedAt": "y"}], settle_t2=[{**base[0], "generatedAt": "y"}]))
    assert any(d["field"] == "settle:generatedAt" and d["classification"] == "regression" for d in r["differences"])
    assert not any(d["field"].endswith("settledAt") for d in r["differences"])


def test_not_measured_or_unrecorded_is_not_run_never_passed(tmp_path):
    diffs = _runs(tmp_path, settle_t1=[{"payout": 0.13, "settledAt": "x", "requestId": "a"}],
                  settle_t2=[{"payout": 0.13, "settledAt": "x", "requestId": "a"}])
    r = V.evaluate(criteria=CRITERIA, mapping={"EC-01": ["claims-read"]}, diffs=diffs, noise={}, design=DESIGN, perf={})
    v = {c["ec_id"]: c for c in r["criteria"]}
    assert (v["EC-02"]["verdict"], v["EC-02"]["cases_compared"]) == ("not_run", None)
    assert v["EC-04"]["verdict"] == "not_run" and r["performance"][0]["target_p95_ms"] is None
    assert V.module_verdict(r["criteria"]) == "open"


def test_a_slow_target_fails_its_threshold():
    r = V.evaluate(criteria=[CRITERIA[2]], mapping={}, diffs={}, noise={}, design=DESIGN,
                   perf={"EC-04": {"legacy_p95_ms": 120.0, "target_p95_ms": 310.0, "samples": 100}})
    assert r["criteria"][0]["verdict"] == "failed"


def test_an_accepted_change_needs_a_regression_and_an_adr_on_the_module(tmp_path):
    wrong = [{"payout": 0.12, "settledAt": "x", "requestId": "z"}]
    r = _evaluate(_runs(tmp_path, settle_t1=wrong, settle_t2=wrong))
    reg = next(d["id"] for d in r["differences"] if d["classification"] == "regression")
    gap = next(d["id"] for d in r["differences"] if d["classification"] == "normalization_gap")
    problems = V.apply_accepted(r, {reg: "ADR-09", gap: "ADR-02", "EQ-999": "ADR-02"}, ["ADR-02"])
    assert any("ADR-09, which is not an ADR on this module" in p for p in problems)
    assert any("not a regression" in p for p in problems) and any("EQ-999 is not a difference" in p for p in problems)
    assert V.apply_accepted(r, {reg: "ADR-02"}, ["ADR-02"]) == []
    assert {c["ec_id"]: c["verdict"] for c in r["criteria"]}["EC-02"] == "open"  # the requestId gap still open


def test_thresholds_and_percentiles():
    assert V.threshold_ms("p95 ≤ 250 ms") == 250.0 and V.threshold_ms("p95 <= 0.5 s") == 500.0
    assert V.threshold_ms("fast") is None and V.threshold_ms(None) is None
    assert V.p95([]) is None and V.p95(range(1, 101)) == 95.0 and V.p95([7]) == 7.0


def test_the_packet_refuses_a_pass_the_evidence_does_not_support():
    base = {"module_id": "M-01", "pr": "p", "baselines_replayed": [{"id": "BL-01", "version": 1}], "runs": 2}
    with pytest.raises(ValueError, match="nothing was compared"):
        EquivalencePayload.model_validate({**base, "criteria": [{"ec_id": "EC-01", "verdict": "passed", "cases_compared": 0}]})
    with pytest.raises(ValueError, match="exceeds"):
        EquivalencePayload.model_validate({**base, "criteria": [{"ec_id": "EC-04", "verdict": "passed", "cases_compared": 5}],
                                           "performance": [{"ec_id": "EC-04", "legacy_p95_ms": 1, "target_p95_ms": 300, "threshold_ms": 250}]})
