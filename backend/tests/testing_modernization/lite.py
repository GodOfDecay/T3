"""ClaimTrack Lite — the sample legacy system (`samples/legacy-claimtrack`) and a migration plan for it.

M-01 is the claims API, M-02 the settlement batch. The plan's criteria are what Equivalence Testing
records: EC-01 (claim reads), EC-02 (settlement payouts — the Python 2 rounding trap), EC-03 (the
bank file, byte for byte after its header's timestamp), EC-04 (a latency percentile: a load test,
not captured in Baseline mode). EC-01 and EC-02 normalize their timestamps but NOT `requestId`, so a
capture must propose a rule for it.
"""
from __future__ import annotations

import copy
import pathlib

SAMPLE = pathlib.Path(__file__).resolve().parents[3] / "samples" / "legacy-claimtrack"


def _wave(wid, name, modules, patterns, starts, ends, exits):
    return {"id": wid, "name": name, "modules": modules, "patterns": patterns, "starts": starts, "ends": ends,
            "date_status": "proposed", "entry_criteria": ["the previous wave's exit met"] if modules else [],
            "exit_criteria": exits, "rollback": {"trigger": "a criterion fails", "method": "switch back"},
            "order_reason": "dependencies first"}


PLAN = {
    "summary": "Move the claims API, then the settlement batch, each proven against the legacy baseline.",
    "waves": [
        _wave("W0", "Foundation", [], {}, "2026-11-02", "2026-11-27", ["baselines accepted"]),
        _wave("W1", "Claims API", ["M-01"], {"M-01": ["in_place_upgrade"]}, "2026-12-01", "2027-01-29",
              ["EC-01", "EC-02", "EC-04"]),
        _wave("W2", "Settlement batch", ["M-02"], {"M-02": ["in_place_upgrade", "strangler_fig"]}, "2027-02-01",
              "2027-03-26", ["EC-03"]),
    ],
    "equivalence_criteria": [
        {"id": "EC-01", "module_id": "M-01", "protects": ["CT-01"], "observable": "GET /api/claims/{id} responses",
         "input_set": "five claims incl. missing", "comparison": "exact",
         "normalization": [{"field": "generatedAt", "rule": "ignore the value", "reason": "generation time"}]},
        {"id": "EC-02", "module_id": "M-01", "protects": ["TR-01"], "observable": "settlement payouts",
         "input_set": "six settlements incl. half-cent cases", "comparison": "exact",
         "normalization": [{"field": "settledAt", "rule": "ignore the value", "reason": "settlement time"}]},
        {"id": "EC-03", "module_id": "M-02", "protects": ["CT-02"], "observable": "BANKPAY file bytes",
         "input_set": "the 31 Jan 2027 run", "comparison": "byte_identical",
         "normalization": [{"field": "BANKPAY_*.txt#L1", "rule": "ignore the generation timestamp",
                            "reason": "the header carries the run time"}]},
        {"id": "EC-04", "module_id": "M-01", "protects": ["CT-01"], "observable": "p95 latency of claim reads",
         "input_set": "200 rps for 10 minutes", "comparison": "percentile_threshold", "threshold": "p95 ≤ 250 ms"},
    ],
    "baseline_plan": [
        {"ec_id": ec, "inputs": "the capture profile's scenarios", "environment": "legacy sandbox",
         "data_source": "synthetic seed", "masking": "synthetic data — nothing to mask", "due": "2026-11-27"}
        for ec in ("EC-01", "EC-02", "EC-03")],
    "freeze_policy": {"from": "2026-11-27", "allowed": "security fixes", "carry_forward": "re-baseline"},
}

MAPPING = {"EC-01": ["claims-read"], "EC-02": ["settle"], "EC-03": ["bank-file"]}
NOT_CAPTURED = [{"ec_id": "EC-04", "reason": "a load test — measured in Verify mode"}]
PROPOSALS = [{"ec_id": "EC-01", "field": "requestId", "rule": "ignore the value, require it present"},
             {"ec_id": "EC-02", "field": "requestId", "rule": "ignore the value, require it present"}]
DESIGNED = {"M-01": ["in_place_upgrade"], "M-02": ["in_place_upgrade", "strangler_fig"]}

#: The noise floor of ClaimTrack Lite AS MEASURED: `test_sandbox` asserts a real two-run capture reproduces
#: exactly this (counts and masked shapes), so the pure tests and the page fixtures built from it are real.
NOISE = {
    "claims-read": {"kind": "http", "cases": 5, "varying": {"generatedAt": 4, "requestId": 5},
                    "examples": {"generatedAt": ["<timestamp>", "<timestamp>"], "requestId": ["<uuid>", "<uuid>"]}},
    "settle": {"kind": "http", "cases": 6, "varying": {"requestId": 6, "settledAt": 4},
               "examples": {"requestId": ["<uuid>", "<uuid>"], "settledAt": ["<timestamp>", "<timestamp>"]}},
    "bank-file": {"kind": "batch", "cases": 1, "varying": {"BANKPAY_20270131.txt#L1": 1},
                  "examples": {"BANKPAY_20270131.txt#L1": ["A99999999999999999999", "A99999999999999999999"]}},
}


def plan() -> dict:
    return copy.deepcopy(PLAN)


def stored_plan() -> dict:
    """As the Strategy page stores it (`StrategyArtifact`) — what the version store holds."""
    from shared.models.artifacts import StrategyArtifact

    return StrategyArtifact(**plan(), system_name="ClaimTrack Lite").model_dump(mode="json")
