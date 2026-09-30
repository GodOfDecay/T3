"""The three deterministic tools the plan starts from (research §6.4), on two unrelated systems.

  propose_wave_order  dependencies first; cycles move together; lowest risk first in a level; kept
                      modules move in no wave; stable for the same inputs
  check_calendar      every kind of conflict, each with its ref; windows read from the user's words
  estimate_effort     a stated table; not measured is "not estimated", never zero
"""
from __future__ import annotations

import pytest

from agents_orchestrator.strategy_agent.analysis import calendar, effort, ordering
from tests.strategy.scenarios import claimtrack, payroll


def _patterns(design):
    return {m["module_id"]: m["patterns"] for m in design["modules"]}


def _order(scenario):
    _b, a, d, _p = scenario
    return ordering.propose_order(a["modules"], [tuple(e) for e in a["graph"]], _patterns(d))


# ── propose_wave_order ───────────────────────────────────────────────────────

def test_claimtrack_dependencies_first_then_lowest_risk():
    o = _order(claimtrack())
    assert [(s["level"], s["modules"]) for s in o["order"]] == [
        (0, ["M-01"]), (0, ["M-05"]), (0, ["M-04"]), (1, ["M-03"]), (1, ["M-02"])]
    assert o["forcing_edges"] == [("M-02", "M-01"), ("M-03", "M-01")] and o["cycles"] == [] and o["kept"] == []


def test_payroll_a_cycle_moves_together_and_a_kept_module_moves_nowhere():
    o = _order(payroll())
    steps = [(s["level"], s["modules"], s["cycle"]) for s in o["order"]]
    assert steps == [(0, ["M-01"], False), (1, ["M-02", "M-03"], True), (2, ["M-04"], False)]
    assert o["cycles"] == [["M-02", "M-03"]] and o["kept"] == ["M-05"]
    assert o["order"][2]["depends_on"] == ["M-01", "M-02"]


def test_a_module_the_design_does_not_have_is_named_not_ordered():
    _b, a, d, _p = payroll()
    d["modules"] = [m for m in d["modules"] if m["module_id"] != "M-05"]
    o = ordering.propose_order(a["modules"], [tuple(e) for e in a["graph"]], _patterns(d))
    assert o["not_in_design"] == ["M-05"] and "M-05" not in {m for s in o["order"] for m in s["modules"]}


def test_the_order_is_stable_and_the_report_says_what_forced_it():
    assert _order(payroll()) == _order(payroll())
    md = ordering.order_markdown(_order(payroll()))
    assert "cycle: must move together" in md and "Kept as they are (move in no wave): M-05." in md


def test_dependency_violations_only_for_a_dependency_in_a_later_wave():
    waves = [{"id": "W1", "modules": ["M-04"]}, {"id": "W2", "modules": ["M-01"]}, {"id": "W10", "modules": ["M-02"]}]
    edges = [("M-04", "M-01"), ("M-02", "M-01"), ("M-04", "M-02")]
    assert ordering.dependency_violations(waves, edges) == [("M-04", "W1", "M-01", "W2"), ("M-04", "W1", "M-02", "W10")]


def test_with_dates_a_dependency_is_ready_first_when_its_wave_ends_first():
    """Wave ids need not run in date order and waves may overlap: the end dates decide."""
    w = lambda i, m, s, e: {"id": i, "modules": [m], "starts": s, "ends": e}  # noqa: E731
    # M-01 depends on M-03. W1 is June, W2 is Feb–Mar: M-03 is ready first despite the higher id.
    assert ordering.dependency_violations([w("W1", "M-01", "2027-06-01", "2027-06-30"),
                                           w("W2", "M-03", "2027-02-01", "2027-03-31")], [("M-01", "M-03")]) == []
    # Swapped: the dependent ships in Feb, its dependency in June — refused though W1 < W2.
    assert ordering.dependency_violations([w("W1", "M-03", "2027-06-01", "2027-06-30"),
                                           w("W2", "M-01", "2027-02-01", "2027-03-31")], [("M-01", "M-03")]) \
        == [("M-01", "W2", "M-03", "W1")]
    # Overlapping waves: the dependency's wave ends after the dependent's — refused.
    assert ordering.dependency_violations([w("W1", "M-03", "2027-01-01", "2027-06-30"),
                                           w("W2", "M-01", "2027-02-01", "2027-04-30")], [("M-01", "M-03")]) \
        == [("M-01", "W2", "M-03", "W1")]


# ── check_calendar ───────────────────────────────────────────────────────────

def test_claimtrack_reports_the_late_cr4_baseline_only():
    b, _a, _d, p = claimtrack()
    assert [c["ref"] for c in calendar.check_calendar(p, b)] == ["baseline-late:EC-03"]


def test_payroll_meets_its_calendar():
    b, _a, _d, p = payroll()
    assert calendar.check_calendar(p, b) == []


def test_every_kind_of_conflict_has_its_ref():
    b, _a, _d, p = payroll()
    b["deadline"] = "2027-06-30"
    p["waves"][3]["cutover_window"] = "Wed 1 Sep 2027 20:00–02:00"  # a weekday, 6 hours
    p["baseline_plan"][0]["due"] = "2027-05-10"  # after the freeze and after W3 starts
    p["waves"][3]["ends"] = "2027-10-15"  # after the deadline and the licence renewal
    refs = [c["ref"] for c in calendar.check_calendar(p, b)]
    assert refs == ["baseline-after-freeze:EC-01", "baseline-late:EC-01", "deadline:W3", "milestone:2027-09-30:W3",
                    "window-day:W3", "window-length:W3"]


@pytest.mark.parametrize("text,days", [
    ("Sunday nights", {6}), ("Sundays only", {6}), ("Sat–Sun", {5, 6}), ("Fri-Mon", {4, 5, 6, 0}),
    ("weekends only", {5, 6}), ("any weekend", {5, 6}), ("weekday evenings", {0, 1, 2, 3, 4}),
    ("Thursday or Saturday", {3, 5}), ("this month", set()),
])
def test_weekdays_are_read_from_the_users_words(text, days):
    assert calendar.days_in(text) == days


@pytest.mark.parametrize("text,minutes", [
    ("at most 2 hours", 120), ("≤ 90 min", 90), ("4h", 240), ("1.5 hours", 90), ("no limit given", None),
])
def test_the_window_limit_is_read(text, minutes):
    assert calendar.limit_minutes(text) == minutes


def test_a_time_range_across_midnight():
    assert calendar.range_minutes("Sat 22:00–01:00") == 180 and calendar.range_minutes("00:00-02:00") == 120
    assert calendar.range_minutes("route by route") is None


@pytest.mark.parametrize("text,days,minutes", [
    ("Friday 22:00 – Monday 06:00", {4, 5, 6, 0}, 56 * 60),
    ("Sat 22:00 to Sun 02:00", {5, 6}, 240),
    ("Sundays 01:00–03:00", {6}, 120),
    ("Sat 27 Feb 2027 22:00–01:00", {5}, 180),
])
def test_windows_that_span_days_or_nights(text, days, minutes):
    assert calendar.days_in(text) == days and calendar.span_minutes(text) == minutes


def test_a_windows_span_is_its_limit_when_none_is_stated():
    plan = {"waves": [{"id": "W1", "modules": ["M-01"], "cutover_window": "Sun 00:00–06:00"}]}
    got = calendar.check_calendar(plan, {"downtime_window": "Sundays 01:00–03:00"})
    assert [c["ref"] for c in got] == ["window-length:W1"]
    stated = calendar.check_calendar(plan, {"downtime_window": "Sundays 01:00–03:00, at most 8 hours"})
    assert stated == []


def test_a_cutover_over_several_days_is_measured_whole():
    plan = {"waves": [{"id": "W1", "modules": ["M-01"], "cutover_window": "Fri 22:00 – Mon 06:00"}]}
    got = calendar.check_calendar(plan, {"downtime_window": "weekends, at most 4 hours"})
    assert [c["ref"] for c in got] == ["window-day:W1", "window-length:W1"]
    assert "3360 min" in got[1]["conflict"]


def test_a_baseline_for_every_module_is_due_before_the_first_move():
    plan = {"waves": [{"id": "W0", "modules": [], "starts": "2027-01-01"},
                      {"id": "W1", "modules": ["M-01"], "starts": "2027-03-01"}],
            "equivalence_criteria": [{"id": "EC-01", "module_id": "all"}],
            "baseline_plan": [{"ec_id": "EC-01", "due": "2027-03-15"}]}
    assert [c["ref"] for c in calendar.check_calendar(plan, {})] == ["baseline-late:EC-01"]


def test_what_could_not_be_read_is_said_by_part():
    assert calendar.window_unread({"downtime_window": "Sundays only"}) == ["length"]
    assert calendar.window_unread({"downtime_window": "at most 2 hours"}) == ["days"]
    assert calendar.window_unread({"downtime_window": "Sat 22:00–02:00"}) == []
    assert calendar.window_unread({}) == []
    assert "checked for days only" in calendar.calendar_markdown([], {"downtime_window": "Sundays only"})


def test_an_unreadable_window_is_said_not_checked():
    b = {"downtime_window": "whenever the business agrees"}
    assert not calendar.window_checked(b)
    assert "could not be read" in calendar.calendar_markdown([], b)


# ── estimate_effort ──────────────────────────────────────────────────────────

def test_payroll_effort_is_a_stated_estimate_per_module_and_wave():
    _b, a, d, p = payroll()
    r = effort.estimate(a["modules"], _patterns(d), p["waves"])
    by = {m["module_id"]: m for m in r["modules"]}
    assert by["M-01"]["days"] == 12.0            # 12 KLOC × mechanical 1.0 × in-place 1.0
    assert by["M-02"]["days"] == pytest.approx(162.0)  # 40 × 3.0 × (1.0 + parallel run 0.35)
    assert by["M-04"]["days"] == pytest.approx(396.0)  # 18 × 8.0 × (rewrite 2.5 + abstraction 0.25)
    assert by["M-05"]["band"] == "not moved"
    assert r["waves"][0] == {"wave": "W0", "band": "15–29 person-days",
                             "basis": "foundation: 10 + 3 × 4 moved modules (assumption)"}
    assert r["is_estimate"] is True and "person-days" in r["total_band"]


def test_a_size_not_measured_is_not_estimated_never_zero():
    _b, a, d, p = claimtrack()  # the ClaimTrack assessment fixture has no LOC
    r = effort.estimate(a["modules"], _patterns(d), p["waves"])
    assert all(m["band"].startswith("not estimated") for m in r["modules"])
    assert all(w["band"] == "not estimated" for w in r["waves"] if w["wave"] != "W0")
    assert r["total_band"].startswith("not estimated")
    assert "ESTIMATE" in effort.effort_markdown(r)
