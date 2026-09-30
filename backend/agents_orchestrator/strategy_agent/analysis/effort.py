"""Effort bands — a STATED table, not a model's guess (research §6.4 `estimate_effort`).

For any system: size (thousands of lines, from the assessment) × how hard each line is to move (the
tier) × what is being done to it (the design's patterns), in person-days, as a ±30 % band. It is an
ESTIMATE and is labelled one everywhere; the basis is returned with it so a person can disagree with
a specific number rather than with a total.

  person-days per KLOC by tier:  mechanical 1.0 · llm_assisted 3.0 · manual 8.0
  the main pattern's factor:     in_place_upgrade 1.0 · replatform 0.5 · rewrite 2.5 · retire 0.3
                                 (branch_by_abstraction / strangler_fig / parallel_run alone: 1.0)
  added per coexistence pattern: strangler_fig +0.25 · branch_by_abstraction +0.25 · parallel_run +0.35
  every moved module:            at least 3 person-days
  the foundation (W0):           10 + 3 per moved module (environments, pipelines, observability,
                                 baseline capture) — an assumption, said so

A module whose size was NOT measured is "not estimated" — never zero (R39) — and so is any wave that
contains one.
"""
from __future__ import annotations

from typing import Optional

PER_KLOC = {"mechanical": 1.0, "llm_assisted": 3.0, "manual": 8.0}
MAIN = {"in_place_upgrade": 1.0, "replatform": 0.5, "rewrite": 2.5, "retire": 0.3}
ADDED = {"strangler_fig": 0.25, "branch_by_abstraction": 0.25, "parallel_run": 0.35}
MINIMUM = 3.0
SPREAD = 0.3
FOUNDATION_BASE, FOUNDATION_PER_MODULE = 10.0, 3.0


def module_estimate(tier: str, loc: Optional[int], patterns: list[str]) -> Optional[float]:
    """Person-days for one module, or None when its size was not measured."""
    if set(patterns or []) <= {"keep"}:
        return 0.0
    if loc is None:
        return None
    main = max((MAIN[p] for p in patterns if p in MAIN), default=1.0)
    added = sum(ADDED[p] for p in patterns if p in ADDED)
    return max(MINIMUM, loc / 1000 * PER_KLOC.get(tier, PER_KLOC["llm_assisted"]) * (main + added))


def band(days: float) -> str:
    return f"{int(days * (1 - SPREAD))}–{int(round(days * (1 + SPREAD)))} person-days"


def estimate(modules: list[dict], patterns: dict[str, list[str]], waves: Optional[list[dict]] = None) -> dict:
    """`modules`: the assessment's [{id, name, tier, loc}]; `patterns`: the design's per module;
    `waves` (optional): the draft plan's waves, to total per wave."""
    per_module = []
    for m in modules:
        ps = patterns.get(m["id"])
        if ps is None:
            continue
        days = module_estimate(m.get("tier") or "", m.get("loc"), ps)
        per_module.append({
            "module_id": m["id"], "name": m.get("name"), "patterns": ps, "days": days,
            "band": band(days) if days else ("not moved" if days == 0 else "not estimated — size not measured"),
            "basis": (f"{(m.get('loc') or 0) / 1000:.1f} KLOC × {m.get('tier')} × {'+'.join(ps)}"
                      if days is not None else "lines of code were not measured by the assessment"),
        })
    by_id = {r["module_id"]: r for r in per_module}
    moved = [r for r in per_module if r["days"] != 0]
    foundation = FOUNDATION_BASE + FOUNDATION_PER_MODULE * len(moved)
    per_wave = []
    for w in waves or []:
        if w.get("id") == "W0":
            per_wave.append({"wave": "W0", "band": band(foundation),
                             "basis": f"foundation: {FOUNDATION_BASE:g} + {FOUNDATION_PER_MODULE:g} × {len(moved)} moved modules (assumption)"})
            continue
        rows = [by_id.get(m) for m in w.get("modules") or []]
        if any(r is None or r["days"] is None for r in rows):
            per_wave.append({"wave": w["id"], "band": "not estimated",
                             "basis": "a module's size was not measured, or it is not in the design"})
            continue
        total = sum(r["days"] for r in rows)
        per_wave.append({"wave": w["id"], "band": band(total),
                         "basis": " + ".join(f"{r['module_id']} {r['basis']}" for r in rows) or "no modules"})
    known = [r["days"] for r in moved if r["days"] is not None]
    total = None if len(known) < len(moved) else sum(known) + foundation
    return {"modules": per_module, "waves": per_wave, "foundation_days": foundation,
            "total_band": band(total) if total is not None else "not estimated — some sizes were not measured",
            "is_estimate": True}


def effort_markdown(result: dict) -> str:
    lines = ["# Effort estimate (an ESTIMATE, not a quote)", "",
             "Person-days from a stated table: size × tier × pattern, ±30 %. Say it is an estimate.", "",
             "| Module | Patterns | Band | Basis |", "|---|---|---|---|"]
    lines += [f"| {r['module_id']} {r['name']} | {', '.join(r['patterns'])} | {r['band']} | {r['basis']} |"
              for r in result["modules"]]
    if result["waves"]:
        lines += ["", "| Wave | Band | Basis |", "|---|---|---|"]
        lines += [f"| {w['wave']} | {w['band']} | {w['basis']} |" for w in result["waves"]]
    lines += ["", f"Total including the foundation: {result['total_band']}."]
    return "\n".join(lines)
