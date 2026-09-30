"""The rules `record_migration_strategy` enforces (analysis/checks.py + PlanPayload), on two systems.

Both plans — ClaimTrack and Payroll, unrelated stacks, shapes and calendars — meet every rule; then
each rule is broken on its own and must refuse with a message naming the item. Pure — no database.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents_orchestrator.modernization_common.handover.packets import PlanPayload
from agents_orchestrator.strategy_agent.tools.strategy_tools import check_plan, placements
from tests.strategy.scenarios import claimtrack, payroll


def _check(scenario, mutate=None):
    brief, assessment, design, plan = scenario
    if mutate:
        mutate(brief, assessment, design, plan)
    data = PlanPayload.model_validate(plan).model_dump(mode="json", by_alias=True)
    return check_plan(data, brief, assessment, design)[0]


def _only(problems, *needles):
    assert len(problems) == 1, problems
    for n in needles:
        assert n in problems[0], problems[0]


@pytest.mark.parametrize("scenario", [claimtrack, payroll])
def test_both_systems_plans_meet_every_rule(scenario):
    assert _check(scenario()) == []


def test_placements_put_each_module_in_its_wave_with_its_criteria():
    _b, _a, _d, p = claimtrack()
    data = PlanPayload.model_validate(p).model_dump(mode="json", by_alias=True)
    got = {x["module_id"]: (x["wave"], x["ec_ids"]) for x in placements(data)}
    assert got == {"M-05": ("W1", ["EC-03", "EC-06", "EC-08"]), "M-01": ("W2", ["EC-01", "EC-08"]),
                   "M-02": ("W2", ["EC-04", "EC-05", "EC-08"]), "M-03": ("W3", ["EC-02", "EC-09", "EC-10", "EC-08"]),
                   "M-04": ("W4", ["EC-07", "EC-08"])}


# ── waves ────────────────────────────────────────────────────────────────────

def test_a_moved_module_in_no_wave_is_refused():
    def drop(b, a, d, p):
        p["waves"][2]["modules"].remove("M-01")
        del p["waves"][2]["patterns"]["M-01"]
        p["equivalence_criteria"] = [c for c in p["equivalence_criteria"] if c["module_id"] != "M-01"]
        p["baseline_plan"] = [x for x in p["baseline_plan"] if x["ec_id"] != "EC-01"]
        p["waves"][2]["exit_criteria"].remove("EC-01")
        for c in p["equivalence_criteria"]:
            if c["id"] == "EC-02":
                c["protects_measures"].append("payouts on 10,000 recorded claims")
    problems = _check(claimtrack(), drop)
    assert any("M-01 is moved by the design (in_place_upgrade) but is in no wave" in x for x in problems), problems


def test_a_kept_module_in_a_wave_is_refused():
    def keep(b, a, d, p):
        p["waves"][1]["modules"].append("M-05")
        p["waves"][1]["patterns"]["M-05"] = ["keep"]
    _only(_check(payroll(), keep), "W1 moves M-05, which the design keeps as it is")


def test_a_module_the_design_lacks_is_refused():
    def extra(b, a, d, p):
        p["waves"][1]["modules"].append("M-09")
        p["waves"][1]["patterns"]["M-09"] = ["rewrite"]
    _only(_check(payroll(), extra), "W1 moves M-09, which the target design does not have")


@pytest.mark.parametrize("patterns,needle", [
    (None, "W3 does not give M-03's patterns"),
    (["rewrite"], "W3 gives M-03 the patterns rewrite, but the design says in_place_upgrade"),
])
def test_the_plan_never_changes_a_pattern(patterns, needle):
    def change(b, a, d, p):
        if patterns is None:
            del p["waves"][3]["patterns"]["M-03"]
        else:
            p["waves"][3]["patterns"]["M-03"] = patterns
    _only(_check(payroll(), change), needle)


# ── order ────────────────────────────────────────────────────────────────────

def test_moving_before_a_dependency_needs_a_design_adr():
    def drop(b, a, d, p):
        p["order_exceptions"] = p["order_exceptions"][:1]  # M-04 before M-02 is no longer covered
    _only(_check(payroll(), drop), "M-04 moves in W1, before M-02 (in W3, which ends later)", "order exception")


def test_an_exception_must_cite_an_adr_the_design_has():
    def cite(b, a, d, p):
        p["order_exceptions"][0]["adr_id"] = "ADR-09"
    _only(_check(payroll(), cite), "cites ADR-09, which the target design does not have")


def test_claimtrack_batch_before_core_is_refused():
    def late(b, a, d, p):
        p["waves"][2]["ends"] = "2027-05-14"  # core (M-01) now cuts over after batch (M-03; W3 ends 25 Apr)
    problems = _check(claimtrack(), late)
    assert any("M-03 moves in W3, before M-01 (in W2, which ends later)" in x for x in problems), problems


def test_wave_ids_are_names_not_the_order():
    # Swapping two waves' ids changes nothing: a dependency is ready first by its wave's END DATE.
    def swap(b, a, d, p):
        p["waves"][3]["id"], p["waves"][2]["id"] = "W2", "W3"
    assert not [x for x in _check(claimtrack(), swap) if "which it depends on" in x]


# ── coverage, exits, baselines ───────────────────────────────────────────────

def test_every_contract_and_trap_needs_a_criterion():
    def drop(b, a, d, p):
        p["equivalence_criteria"][1]["protects"] = ["CT-01"]  # EC-02 no longer covers TR-01
        p["equivalence_criteria"][0]["protects"] = ["CT-01"]  # nor EC-01
    _only(_check(payroll(), drop), "No criterion covers TR-01 (decimal rounding in .NET Core Math.Round)")
    def drop_ct(b, a, d, p):
        p["equivalence_criteria"][0]["protects"] = ["TR-01"]
    _only(_check(payroll(), drop_ct), "No criterion protects CT-01 (BACS payment file)")


def test_every_proven_measure_needs_a_criterion_in_the_briefs_words():
    def reword(b, a, d, p):
        p["equivalence_criteria"][2]["protects_measures"] = ["the payslip speed"]
    problems = _check(payroll(), reword)
    assert any("performance measure “payslip page p95” is protected by no criterion" in x for x in problems)
    assert any("EC-03 protects the measure “the payslip speed”, which is not a success measure" in x for x in problems)


def test_a_cost_or_schedule_measure_needs_no_criterion():
    assert "licence savings" in [m["metric"] for m in payroll()[0]["success_measures"]]
    assert _check(payroll()) == []


def test_criteria_cite_only_what_the_design_defines():
    def bad(b, a, d, p):
        p["equivalence_criteria"][1]["protects"] = ["TR-01", "CT-07"]
    _only(_check(payroll(), bad), "EC-02 protects CT-07, which the design does not define")


def test_a_waves_exits_include_its_modules_criteria():
    def drop(b, a, d, p):
        p["waves"][3]["exit_criteria"] = ["EC-01", "three identical runs"]
    _only(_check(payroll(), drop), "W3's exit criteria do not include EC-02")


def test_a_contract_or_trap_criterion_needs_a_baseline():
    def drop(b, a, d, p):
        p["baseline_plan"] = p["baseline_plan"][:1]
    _only(_check(payroll(), drop), "EC-02 protects TR-01 but has no baseline")


def test_a_parallel_run_needs_its_period():
    def drop(b, a, d, p):
        p["waves"][3]["parallel_run"] = {"required": True, "period": "", "system_of_record": "legacy"}
    _only(_check(payroll(), drop), "W3 moves M-02 by parallel run", "period")


# ── dates, effort ────────────────────────────────────────────────────────────

def test_the_briefs_freeze_date_is_kept():
    def move(b, a, d, p):
        p["freeze_policy"]["from"] = "2027-04-01"
    _only(_check(payroll(), move), "The brief freezes the legacy system from 2027-03-01; the plan says 2027-04-01")


def test_every_computed_calendar_conflict_must_be_reported_by_ref():
    def late(b, a, d, p):
        p["waves"][3]["cutover_window"] = "Wed 1 Sep 2027 20:00–23:00"
    _only(_check(payroll(), late), "Calendar conflict not reported", "window-day:W3")
    def reported(b, a, d, p):
        late(b, a, d, p)
        p["calendar_conflicts"] = [{"conflict": "Wednesday cutover", "impact": "not agreed", "ref": "window-day:W3"}]
    assert _check(payroll(), reported) == []


def test_given_dates_must_be_the_briefs():
    def claim(b, a, d, p):
        p["waves"][3]["date_status"] = "given"
    _only(_check(payroll(), claim), "W3's dates are marked given, but neither 2027-05-03 nor 2027-08-27")
    def from_brief(b, a, d, p):
        p["waves"][2]["date_status"] = "given"  # W2 starts 2027-03-01, the brief's freeze milestone
    assert _check(payroll(), from_brief) == []


def test_a_night_cutover_may_end_the_next_morning_within_the_windows_own_span():
    def night(b, a, d, p):
        b["downtime_window"] = "Saturday nights 22:00–02:00"  # no stated limit: its span, 240 min, is the limit
        p["waves"][1]["cutover_window"] = "Sat 22:00 – Sun 01:30"
        p["waves"][2]["cutover_window"] = "Sat 22:00–01:00"
        p["waves"][3]["cutover_window"] = "Sat 22:00–02:00"
    assert _check(payroll(), night) == []
    def too_long(b, a, d, p):
        night(b, a, d, p)
        p["waves"][3]["cutover_window"] = "Sat 20:00–02:00"
    _only(_check(payroll(), too_long), "window-length:W3")
    def other_night(b, a, d, p):
        night(b, a, d, p)
        p["waves"][2]["cutover_window"] = "Sun 22:00–01:00"
    _only(_check(payroll(), other_night), "window-day:W2")


def test_every_wave_has_effort_and_a_budget_gets_an_answer():
    def drop(b, a, d, p):
        p["effort"] = p["effort"][:3]
        b["budget"] = "£400k"
    problems = _check(payroll(), drop)
    assert any("W3 has no effort line" in x for x in problems)
    assert any("The brief has a budget (£400k)" in x for x in problems)


# ── the packet itself ────────────────────────────────────────────────────────

@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["waves"][1]["exit_criteria"].append("EC-42"), "wave criteria cite criteria the plan does not define: EC-42"),
    (lambda p: p["order_exceptions"].append({"module_id": "M-05", "depends_on": "M-01", "reason": "x",
                                             "adr_id": "ADR-01"}), "order exceptions name modules that are in no wave: M-05"),
    (lambda p: p["calendar_conflicts"].extend([{"conflict": "a", "impact": "b", "ref": "x"},
                                               {"conflict": "c", "impact": "d", "ref": "x"}]), "calendar conflict refs must be unique"),
    (lambda p: p["waves"][0].update(modules=["M-04"], patterns={"M-04": ["rewrite"]}),
     "W0 is the foundation and moves no module; put M-04 in W1 or later"),
    (lambda p: p["waves"][1].update(entry_criteria=[" "]), "W1 has no entry criteria"),
])
def test_the_packet_refuses_what_it_can_see_alone(mutate, needle):
    _b, _a, _d, p = payroll()
    mutate(p)
    with pytest.raises(ValidationError, match=needle):
        PlanPayload.model_validate(p)
