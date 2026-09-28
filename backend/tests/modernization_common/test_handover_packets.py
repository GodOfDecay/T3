"""The Track 3 hand-over contracts: fixtures validate, schemas are pinned, every rule refuses.

Pure unit tests: no database, no model, no network.

Each refusal test starts from the VALID ClaimTrack fixture and breaks exactly one thing, so a
refusal cannot come from some other defect in the input, and asserts the rule's own message
(R47: the specific failure, not "some exception was raised").
"""
from __future__ import annotations

import copy
import json
import re

import pytest
from pydantic import ValidationError

from agents_orchestrator.modernization_common.handover import (
    FIXTURE_DIR, PACKETS, SCHEMA_DIR, load_fixture, render_schema,
)
from agents_orchestrator.modernization_common.handover.ids import mint

pytestmark = pytest.mark.unit


def _raw(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _refused(name: str, mutate, match: str) -> None:
    data = copy.deepcopy(_raw(name))
    PACKETS[name].model_validate(data)  # the control: the unmutated fixture is valid
    mutate(data["payload"])
    with pytest.raises(ValidationError, match=match):
        PACKETS[name].model_validate(data)


# ── every fixture validates; schemas are pinned ──────────────────────────────

def test_there_is_a_fixture_and_a_schema_for_every_packet_and_nothing_else():
    assert sorted(p.stem for p in FIXTURE_DIR.glob("*.json")) == sorted(PACKETS)
    assert sorted(p.stem for p in SCHEMA_DIR.glob("*.json")) == sorted(PACKETS)
    assert len(PACKETS) == 10


@pytest.mark.parametrize("name", sorted(PACKETS))
def test_claimtrack_fixture_validates(name):
    packet = load_fixture(name)
    assert packet.schema_version == 1
    assert packet.artifact == PACKETS[name].model_fields["artifact"].default


@pytest.mark.parametrize("name", sorted(PACKETS))
def test_checked_in_schema_matches_the_model(name):
    on_disk = (SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert on_disk == render_schema(name), (
        f"schemas/{name}.json is stale — run "
        "`uv run python -m agents_orchestrator.modernization_common.handover`")


def test_unknown_field_is_refused_not_dropped():
    data = _raw("design")
    data["payload"]["modules"][0]["pattern"] = "in_place_upgrade"  # typo of `patterns`
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PACKETS["design"].model_validate(data)


def test_one_pin_per_input():
    data = _raw("design")
    data["built_from"].append(dict(data["built_from"][0], version=2))
    with pytest.raises(ValidationError, match="built_from artifacts must be unique"):
        PACKETS["design"].model_validate(data)


# ── ids ──────────────────────────────────────────────────────────────────────

def test_mint_widths_and_refusals():
    assert (mint("M", 2), mint("CT", 4), mint("F", 12), mint("EQ", 31)) == ("M-02", "CT-04", "F-012", "EQ-031")
    with pytest.raises(ValueError, match="no id scheme"):
        mint("W", 1)
    with pytest.raises(ValueError, match="ids start at 1"):
        mint("M", 0)


def test_malformed_id_is_refused():
    _refused("design", lambda p: p["frozen_contracts"][0].update(id="CT-1"),
             r"String should match pattern '\^CT-")


# ── 1 brief, 2 assessment ────────────────────────────────────────────────────

def test_brief_success_measure_needs_a_known_kind():
    _refused("brief", lambda p: p["success_measures"][0].update(kind="quality"),
             "'equivalence', 'performance', 'security', 'schedule' or 'cost'")


def test_brief_must_not_change_entry_cannot_be_blank():
    _refused("brief", lambda p: p["must_not_change"].append("  "), "must_not_change has an empty entry")


def test_assessment_graph_edge_to_unknown_module():
    _refused("assessment", lambda p: p["graph"].append(["M-02", "M-09"]), "names unknown module")


def test_assessment_golden_master_pointer_must_match_status():
    _refused("assessment", lambda p: p["golden_master"].update(status="captured"),
             "captured but names no baseline")


# ── 3 design (record_target_design) ──────────────────────────────────────────

def test_design_module_with_no_pattern():
    _refused("design", lambda p: p["modules"][0].update(patterns=[]), "at least 1 item")


def test_design_pattern_outside_vocabulary():
    _refused("design", lambda p: p["modules"][0].update(patterns=["lift_and_shift"]), "'in_place_upgrade'")


def test_design_contract_with_no_legacy_location():
    _refused("design", lambda p: p["frozen_contracts"][0].update(legacy_location=""), "legacy_location")


def test_design_adr_with_one_option():
    _refused("design", lambda p: p["adrs"][0].update(options=["only one"]), "at least 2 items")


def test_design_reference_to_undefined_contract():
    _refused("design", lambda p: p["modules"][1].update(contract_ids=["CT-09"]),
             "module contract_ids cite ids this design does not define: CT-09")


# ── 4 plan (record_migration_strategy) ───────────────────────────────────────

def test_plan_module_in_two_waves():
    _refused("plan", lambda p: p["waves"][2]["modules"].append("M-05"),
             "modules placed in more than one wave: M-05")


def test_plan_without_w0():
    _refused("plan", lambda p: p.update(waves=[w for w in p["waves"] if w["id"] != "W0"]), "there is no W0")


def test_plan_criterion_without_observable():
    _refused("plan", lambda p: p["equivalence_criteria"][0].update(observable=""), "observable")


def test_plan_criterion_with_vague_comparison():
    _refused("plan", lambda p: p["equivalence_criteria"][0].update(comparison="works the same"), "'exact'")


def test_plan_normalization_rule_without_reason():
    _refused("plan", lambda p: p["equivalence_criteria"][1]["normalization"][0].update(reason=""), "reason")


def test_plan_wave_without_rollback():
    _refused("plan", lambda p: p["waves"][1].pop("rollback"), r"rollback\n\s+Field required")


def test_plan_percentile_without_threshold():
    _refused("plan", lambda p: p["equivalence_criteria"][4].update(threshold=None),
             "EC-05 compares by percentile_threshold but gives no threshold")


def test_plan_criterion_protecting_nothing():
    _refused("plan", lambda p: p["equivalence_criteria"][0].update(protects=[], protects_measures=[]),
             "EC-01 protects nothing")


def test_plan_baseline_item_for_undefined_criterion():
    _refused("plan", lambda p: p["baseline_plan"][0].update(ec_id="EC-42"), "criteria the plan does not define: EC-42")


# ── 5 baseline ───────────────────────────────────────────────────────────────

def test_baseline_uncovered_noise_must_be_proposed_not_ignored():
    _refused("baseline", lambda p: p.update(rule_proposals=[]),
             "error.requestId varies between legacy runs for EC-04 and no rule covers it")


def test_baseline_hash_must_be_sha256():
    _refused("baseline", lambda p: p["baselines"][0].update(sha256="abc"), "sha256")


# ── 6 migration record (record_module_migration) ─────────────────────────────

def test_record_dropped_file_needs_a_reason():
    _refused("migration_record", lambda p: p["file_map"][0].update(disposition="dropped", target_path=None),
             "dropped without a reason")


def test_record_file_outside_the_module():
    _refused("migration_record",
             lambda p: p["file_map"].append({"legacy_path": "claimtrack-web/pom.xml", "disposition": "mapped",
                                             "target_path": "claimtrack-web/pom.xml"}),
             "outside claimtrack-reports: claimtrack-web/pom.xml")


def test_record_ready_for_review_needs_a_green_build():
    _refused("migration_record", lambda p: p["build"].update(status="red", failing="tests"),
             "the build is red; only a green build is ready for review")


def test_record_stops_after_five_rounds():
    _refused("migration_record", lambda p: p["build"].update(rounds=6), "less than or equal to 5")


def test_record_manual_tier_writes_no_code():
    def mutate(p):
        p.update(outcome="blocked", handoff_note="redesign the scheduler")
    _refused("migration_record", mutate, "a blocked .* module has no code written")


def test_record_recipe_must_be_pinned():
    _refused("migration_record", lambda p: p["recipes"][1].update(version="latest"), "is not pinned")


# ── 7 review (submit_migration_review) ───────────────────────────────────────

def test_review_cannot_approve_its_own_blocking_findings():
    _refused("review", lambda p: p.update(merge_recommendation="approve"),
             "F-003 force request_changes")


def test_review_approve_refused_with_unhandled_trap_even_without_findings():
    def mutate(p):
        p.update(merge_recommendation="approve", findings=[])
    _refused("review", mutate, "cannot approve — traps not handled: TR-04")


# ── 8 security report (Track 3 sign-off policy) ──────────────────────────────

def test_security_pass_with_reachable_carried_over_high():
    _refused("security_report", lambda p: p.update(verdict="PASS"), "the policy gives FAIL, not PASS")


def test_security_unknown_reachability_counts_as_reachable():
    _refused("security_report", lambda p: (p["findings"][0].update(reachable=None), p.update(verdict="CONDITIONAL")),
             "the policy gives FAIL, not CONDITIONAL")


def test_security_carried_over_secret_fails_whatever_its_severity():
    def mutate(p):
        p["findings"][0].update(severity="low", reachable=False, is_secret=True,
                                remediation_plan="rotate", remediation_due="2027-01-15")
        p.update(verdict="CONDITIONAL")
    _refused("security_report", mutate, "the policy gives FAIL, not CONDITIONAL")


def test_security_not_scanned_is_not_clean():
    def mutate(p):
        p.update(findings=[], verdict="PASS", rationale="clean")
        p["scans"]["gitleaks"] = "not_installed"
    _refused("security_report", mutate, "cannot PASS: gitleaks did not run")


def test_security_conditional_needs_a_remediation_date():
    def mutate(p):
        p["findings"][0].update(severity="medium")
        p.update(verdict="CONDITIONAL")
    _refused("security_report", mutate, "CONDITIONAL needs a remediation plan and a date for S-002")


# ── 9 equivalence results ────────────────────────────────────────────────────

def test_equivalence_not_run_is_never_passed():
    _refused("equivalence_results", lambda p: p["criteria"][0].update(cases_compared=None),
             "EC-03 cannot pass: nothing was compared")


def test_equivalence_regression_fails_the_criterion():
    _refused("equivalence_results",
             lambda p: p["differences"].append({"id": "EQ-004", "ec_id": "EC-06", "classification": "regression",
                                                "field": "avg_settlement_days", "cases": 3,
                                                "masked_example": "row R-***: 4.33 vs 4.34"}),
             "EC-06 has a regression and cannot pass")


def test_equivalence_normalization_gap_keeps_the_criterion_open():
    _refused("equivalence_results",
             lambda p: p["differences"].append({"id": "EQ-005", "ec_id": "EC-03", "classification": "normalization_gap",
                                                "field": "run id", "cases": 1, "masked_example": "***"}),
             "EC-03 has a normalization gap")


def test_equivalence_accepted_change_cites_an_adr():
    _refused("equivalence_results",
             lambda p: p["differences"].append({"id": "EQ-006", "ec_id": "EC-06", "classification": "accepted_change",
                                                "field": "x", "cases": 1, "masked_example": "***"}),
             "EQ-006 is an accepted change but cites no ADR")


def test_equivalence_performance_over_threshold():
    _refused("equivalence_results",
             lambda p: p["performance"].append({"ec_id": "EC-06", "legacy_p95_ms": 812, "target_p95_ms": 340,
                                                "threshold_ms": 300}),
             "EC-06 target p95 340.0 ms exceeds 300.0 ms")


def test_equivalence_verdict_of_the_module():
    packet = load_fixture("equivalence_results")
    assert packet.payload.module_verdict() == "verified"


# ── 10 cutover plan ──────────────────────────────────────────────────────────

def test_cutover_red_gate_is_no_go():
    _refused("cutover_plan", lambda p: p["readiness"][0].update(security="red"), "NO-GO: .*M-05: security")


def test_cutover_waived_red_is_go():
    data = _raw("cutover_plan")
    data["payload"]["readiness"][0].update(
        security="red", waivers=[{"gate": "security", "approver": "u-sec", "reason": "documented exception"}])
    assert PACKETS["cutover_plan"].model_validate(data).payload.go is True


def test_cutover_downtime_over_the_window_must_be_reported():
    _refused("cutover_plan", lambda p: p["steps"][2].update(minutes=180, counts_as_downtime=True),
             "planned downtime is 180 min against a 120-min window; downtime_exceeds_window must be true")


def test_cutover_one_sender_per_day():
    _refused("cutover_plan",
             lambda p: p["parallel_runs"][0]["days"].append({"day": "2027-01-04", "sender": "new"}),
             "a day appears twice")


def test_cutover_traffic_shift_must_end_at_100():
    _refused("cutover_plan",
             lambda p: p.update(traffic_shift=[
                 {"step_id": "CO-1.5", "percent": 5, "hold": "1d", "guards": ["p95"]},
                 {"step_id": "CO-1.6", "percent": 50, "hold": "1d", "guards": ["p95"]}]),
             r"traffic shift \[5, 50\] must only increase and end at 100")


def test_cutover_decommission_before_hypercare_closes():
    _refused("cutover_plan",
             lambda p: p.update(decommission=[{"id": "CO-D.1", "item": "archive legacy repo", "order": 1}]),
             "decommission is refused while hypercare is not_started")


def test_cutover_release_needs_two_people():
    _refused("cutover_plan", lambda p: p["sign_off"][1].update(user_id="fixture:devops-2"),
             "one person holds both release sign-off slots")


def test_fixture_does_not_contain_the_refusal_texts():
    """R47: an assertion must not be satisfiable by the fixture echoing the message."""
    blob = " ".join((FIXTURE_DIR / f"{n}.json").read_text(encoding="utf-8") for n in PACKETS)
    for text in ("NO-GO", "cannot pass", "force request_changes", "policy gives", "not pinned"):
        assert not re.search(re.escape(text), blob)
