"""The rules a migration plan must meet that need MORE than the plan itself (decision D7).

`PlanPayload` refuses what the plan alone shows is wrong (no W0, a module in two waves, a criterion
without an observable, a rule without a reason, a wave without a rollback). What needs the brief, the
assessment or the design lives here, each as a small pure function — for ANY system, in terms of the
dependency graph, the design's patterns, contracts and traps, and the brief's measures and dates:

  waves       every module the design moves is in exactly one wave, with the design's patterns
              (the plan never changes a pattern); a module the design keeps moves in no wave
  order       nothing moves before what it depends on, unless an order exception cites a design ADR
  coverage    every frozen contract, every trap, and every equivalence / performance / security
              success measure (in the brief's words) is protected by a criterion; criteria cite
              only modules, contracts and traps the design defines
  exits       every wave's exit criteria include the criteria of the modules it moves
  baselines   every criterion that protects a contract or a trap has a baseline to record first
  parallel    a module whose pattern is parallel_run moves in a wave that says how long it runs
  dates       the brief's freeze date is the plan's; every conflict the calendar check computes is
              reported (by its ref)
  effort      every wave has an effort line; a brief with a budget gets an answer on budget fit

Every message is the refusal the model reads, so each names the item and says what to do.
"""
from __future__ import annotations

import re
from typing import Iterable

from agents_orchestrator.design_modernization_agent.analysis.checks import words
from agents_orchestrator.strategy_agent.analysis.ordering import dependency_violations, moved_modules

#: Measure kinds a criterion must protect: behaviour, speed and security are proven by testing;
#: schedule and cost are the plan's own dates and effort, not criteria.
PROVEN_KINDS = ("equivalence", "performance", "security")


def check_waves(waves: list[dict], patterns: dict[str, list[str]]) -> list[str]:
    moved = moved_modules(patterns)
    placed = {m: w for w in waves for m in w.get("modules") or []}
    problems = []
    for m in sorted(moved - set(placed)):
        problems.append(f"{m} is moved by the design ({'+'.join(patterns[m])}) but is in no wave. Put it in "
                        "exactly one wave.")
    for m, w in sorted(placed.items()):
        if m not in patterns:
            problems.append(f"{w['id']} moves {m}, which the target design does not have. Plan only the "
                            "design's modules; a new module is a design revision first.")
            continue
        if m not in moved:
            problems.append(f"{w['id']} moves {m}, which the design keeps as it is. Leave it out of the waves, "
                            "or ask for a design revision.")
            continue
        given = (w.get("patterns") or {}).get(m)
        if given is None:
            problems.append(f"{w['id']} does not give {m}'s patterns: copy the design's ({', '.join(patterns[m])}).")
        elif sorted(given) != sorted(patterns[m]):
            problems.append(f"{w['id']} gives {m} the patterns {', '.join(given)}, but the design says "
                            f"{', '.join(patterns[m])}. The plan never changes a pattern — ask Target Architecture "
                            "for a revision instead.")
    return problems


def check_order(waves: list[dict], edges: Iterable[tuple[str, str]], exceptions: list[dict],
                design_adrs: set[str]) -> list[str]:
    allowed = {(x["module_id"], x["depends_on"]): x for x in exceptions}
    problems = []
    for dependent, dw, dependency, lw in dependency_violations(waves, edges):
        x = allowed.get((dependent, dependency))
        if x is None:
            problems.append(f"{dependent} moves in {dw}, before {dependency} (in {lw}, which ends later), which it "
                            f"depends on. Move {dependency} to a wave that ends no later than {dw}, or add an order "
                            "exception citing the design ADR that says how both sides coexist meanwhile.")
    for x in exceptions:
        if x["adr_id"] not in design_adrs:
            problems.append(f"The order exception for {x['module_id']} before {x['depends_on']} cites {x['adr_id']}, "
                            "which the target design does not have. Cite the ADR that allows it, or ask for one.")
    return problems


def check_coverage(criteria: list[dict], design: dict, brief_measures: list[dict]) -> list[str]:
    contracts = {c["id"] for c in design.get("frozen_contracts") or []}
    traps = {t["id"] for t in design.get("traps") or []}
    modules = {m["module_id"] for m in design.get("modules") or []}
    problems = []
    for c in criteria:
        if c["module_id"] != "all" and c["module_id"] not in modules:
            problems.append(f"{c['id']} is for {c['module_id']}, which the target design does not have.")
        unknown = sorted(set(c.get("protects") or []) - contracts - traps)
        if unknown:
            problems.append(f"{c['id']} protects {', '.join(unknown)}, which the design does not define.")
    protected = {p for c in criteria for p in c.get("protects") or []}
    for cid in sorted(contracts - protected):
        name = next(c["name"] for c in design["frozen_contracts"] if c["id"] == cid)
        problems.append(f"No criterion protects {cid} ({name}). Every frozen contract is proven unchanged by at "
                        "least one criterion.")
    for tid in sorted(traps - protected):
        change = next(t["change"] for t in design["traps"] if t["id"] == tid)
        problems.append(f"No criterion covers {tid} ({change}). Every trap becomes a criterion of its own or is "
                        "named in one's protects.")
    measured = {words(m["metric"]): m for m in brief_measures if m.get("kind") in PROVEN_KINDS}
    covered = {words(x) for c in criteria for x in c.get("protects_measures") or []}
    for key, m in measured.items():
        if key not in covered:
            problems.append(f"The brief's {m['kind']} measure “{m['metric']}” is protected by no criterion. Add one "
                            "with protects_measures holding exactly those words.")
    known = {words(m["metric"]) for m in brief_measures}
    for c in criteria:
        for x in c.get("protects_measures") or []:
            if words(x) not in known:
                problems.append(f"{c['id']} protects the measure “{x}”, which is not a success measure of the brief. "
                                "Copy the brief's words exactly.")
    return problems


def check_exits(waves: list[dict], criteria: list[dict]) -> list[str]:
    by_module: dict[str, list[str]] = {}
    for c in criteria:
        by_module.setdefault(c["module_id"], []).append(c["id"])
    problems = []
    for w in waves:
        if w["id"] == "W0" or not w.get("modules"):
            continue
        cited = {ec for text in w.get("exit_criteria") or [] for ec in re.findall(r"\bEC-\d{2,}\b", text)}
        needed = sorted({ec for m in w["modules"] for ec in by_module.get(m, [])} | set(by_module.get("all", [])))
        missing = [ec for ec in needed if ec not in cited]
        if missing:
            problems.append(f"{w['id']}'s exit criteria do not include {', '.join(missing)}, which prove the modules "
                            "it moves. A wave is done when its modules' criteria pass.")
    return problems


def check_baselines(criteria: list[dict], baseline_plan: list[dict]) -> list[str]:
    planned = {b["ec_id"] for b in baseline_plan}
    return [f"{c['id']} protects {', '.join(c['protects'])} but has no baseline in the plan. Say what Equivalence "
            "Testing records from the legacy system first: inputs, environment, data source, masking, due date."
            for c in criteria if c.get("protects") and c["id"] not in planned]


def check_parallel_runs(waves: list[dict], patterns: dict[str, list[str]]) -> list[str]:
    problems = []
    for w in waves:
        runs = [m for m in w.get("modules") or [] if "parallel_run" in patterns.get(m, [])]
        pr = w.get("parallel_run") or {}
        if runs and not (pr.get("required") and (pr.get("period") or "").strip()):
            problems.append(f"{w['id']} moves {', '.join(runs)} by parallel run, so the wave needs parallel_run "
                            "required with its period (how long the old side stays the system of record).")
    return problems


def check_dates(plan: dict, brief: dict, computed: list[dict]) -> list[str]:
    problems = []
    freeze = brief.get("freeze_from")
    given = (plan.get("freeze_policy") or {}).get("from")
    if freeze and str(given) != str(freeze):
        problems.append(f"The brief freezes the legacy system from {freeze}; the plan says {given}. A date the user "
                        "gave is not moved — use it, and raise a conflict if it does not work.")
    brief_dates = {str(d) for d in (brief.get("deadline"), freeze) if d}
    brief_dates |= {str(m["date"]) for m in brief.get("milestones") or [] if m.get("date")}
    for w in plan.get("waves") or []:
        if w.get("date_status") == "given" and not {str(w.get("starts")), str(w.get("ends"))} & brief_dates:
            problems.append(f"{w['id']}'s dates are marked given, but neither {w.get('starts')} nor {w.get('ends')} "
                            "is a date in the brief. Mark them proposed, or record the date in the brief first.")
    reported = {c.get("ref") for c in plan.get("calendar_conflicts") or [] if c.get("ref")}
    for c in computed:
        if c["ref"] not in reported:
            problems.append(f"Calendar conflict not reported: {c['conflict']}. Add it to calendar_conflicts with "
                            f"ref “{c['ref']}”, its impact and the options, and tell the user.")
    return problems


def check_effort(plan: dict, brief: dict) -> list[str]:
    have = {e["wave"] for e in plan.get("effort") or []}
    problems = [f"{w['id']} has no effort line. Give an estimate band for every wave (estimate_effort)."
                for w in plan.get("waves") or [] if w["id"] not in have]
    if brief.get("budget") and not (plan.get("budget_fit") or "").strip():
        problems.append(f"The brief has a budget ({brief['budget']}); say whether the plan fits it and what that rests on.")
    return problems
