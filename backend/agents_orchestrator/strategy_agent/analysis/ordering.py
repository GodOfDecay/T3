"""A dependency-safe wave order, for ANY system — deterministic (research §6.4 `propose_wave_order`).

THE RULE. A module moves no earlier than what it depends on: the assessment's graph says
`dependent → dependency`, and the dependency is ready first (same wave or earlier). Everything
else is a choice the agent justifies.

HOW.
  1. Only modules the design MOVES take part. A module whose patterns are only `keep` stays where it
     is and is listed as kept; an edge to it does not constrain anything.
  2. Modules that depend on each other in a CYCLE (strongly connected components, Tarjan) cannot be
     separated safely: they are one step, reported as a cycle, and must move together — or the design
     must say (an ADR) how one side runs against the other in between.
  3. The steps are layered: a step's level is one more than the deepest step it depends on. Within a
     level, lowest risk first (the highest risk score in the step), then by id — the research's
     "lowest risk first by default", and stable for the same inputs.

The result is a PROPOSAL the agent starts from; every change it makes to it is stated and, where it
breaks a dependency, must cite a design ADR (`checks.check_order`).
"""
from __future__ import annotations

import re
from typing import Iterable


def _id_key(module_id: str) -> tuple[int, str]:
    digits = re.sub(r"\D", "", module_id)
    return (int(digits) if digits else 0, module_id)


def moved_modules(patterns: dict[str, list[str]]) -> set[str]:
    """Modules the design moves: any pattern other than `keep`."""
    return {m for m, ps in patterns.items() if any(p != "keep" for p in ps or [])}


def _components(nodes: list[str], deps: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's strongly connected components (iterative), each sorted by id."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(deps.get(root, ()), key=_id_key)))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(deps.get(child, ()), key=_id_key))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(sorted(comp, key=_id_key))
    return out


def propose_order(modules: list[dict], edges: Iterable[tuple[str, str]],
                  patterns: dict[str, list[str]]) -> dict:
    """`modules`: [{id, name, score}] (the assessment); `edges`: (dependent, dependency);
    `patterns`: module id → the design's patterns. Returns the proposal (see module docstring)."""
    info = {m["id"]: m for m in modules}
    moved = sorted(moved_modules(patterns) & set(info), key=_id_key)
    kept = sorted((set(patterns) & set(info)) - set(moved), key=_id_key)
    deps: dict[str, set[str]] = {m: set() for m in moved}
    forcing: list[tuple[str, str]] = []
    for dependent, dependency in edges:
        if dependent in deps and dependency in deps and dependent != dependency:
            deps[dependent].add(dependency)
            forcing.append((dependent, dependency))
    comps = _components(moved, deps)
    comp_of = {m: i for i, c in enumerate(comps) for m in c}
    comp_deps = {i: {comp_of[d] for m in c for d in deps[m] if comp_of[d] != i} for i, c in enumerate(comps)}
    level: dict[int, int] = {}

    def depth(i: int) -> int:
        if i not in level:
            level[i] = 0  # components form a DAG, so this cannot recurse forever
            level[i] = 1 + max((depth(j) for j in comp_deps[i]), default=-1)
        return level[i]

    for i in range(len(comps)):
        depth(i)
    steps = sorted(range(len(comps)), key=lambda i: (
        level[i], max(int(info[m].get("score") or 0) for m in comps[i]), _id_key(comps[i][0])))
    order = []
    for n, i in enumerate(steps, 1):
        members = comps[i]
        order.append({
            "step": n, "level": level[i], "modules": members,
            "names": [info[m].get("name") or m for m in members],
            "max_risk": max(int(info[m].get("score") or 0) for m in members),
            "cycle": len(members) > 1,
            "depends_on": sorted({d for m in members for d in deps[m]} - set(members), key=_id_key),
        })
    return {
        "order": order,
        "kept": kept,
        "cycles": [c for c in comps if len(c) > 1],
        "forcing_edges": sorted(set(forcing), key=lambda e: (_id_key(e[0]), _id_key(e[1]))),
        "not_in_design": sorted(set(info) - set(patterns), key=_id_key),
    }


def wave_number(wave_id: str) -> int:
    return int(wave_id[1:]) if re.fullmatch(r"W\d+", wave_id or "") else 10**6


def dependency_violations(waves: list[dict], edges: Iterable[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """(dependent, its wave, dependency, its wave) where the dependency is NOT ready first.

    A module is cut over when its wave ends, and waves may overlap or run in any id order, so "ready
    first" is by date: the dependency's wave ends on or before the dependent's. Only when a wave has no
    end date is the wave number the order."""
    wave_of = {m: w["id"] for w in waves for m in w.get("modules") or []}
    ends = {w["id"]: str(w["ends"]) for w in waves if w.get("ends")}
    out = []
    for dependent, dependency in edges:
        a, b = wave_of.get(dependent), wave_of.get(dependency)
        if not (a and b) or dependent == dependency or a == b:
            continue
        later = ends[b] > ends[a] if a in ends and b in ends else wave_number(b) > wave_number(a)
        if later:
            out.append((dependent, a, dependency, b))
    return sorted(set(out), key=lambda v: (_id_key(v[0]), _id_key(v[2])))


def order_markdown(proposal: dict) -> str:
    lines = ["# Dependency-safe order (proposal)", "",
             "Dependencies first; within a level, lowest risk first. Start from this order and give the "
             "reason for every change — moving a module before what it depends on needs a design ADR.", "",
             "| Step | Level | Modules | Highest risk | Waits for | Note |", "|---:|---:|---|---:|---|---|"]
    for s in proposal["order"]:
        mods = ", ".join(f"{m} {n}" for m, n in zip(s["modules"], s["names"]))
        lines.append(f"| {s['step']} | {s['level']} | {mods} | {s['max_risk']} | "
                     f"{', '.join(s['depends_on']) or '—'} | {'cycle: must move together' if s['cycle'] else ''} |")
    if proposal["kept"]:
        lines += ["", "Kept as they are (move in no wave): " + ", ".join(proposal["kept"]) + "."]
    if proposal["not_in_design"]:
        lines += ["", "In the assessment but not in the design: " + ", ".join(proposal["not_in_design"])
                  + " — the design must give them a pattern first."]
    if proposal["forcing_edges"]:
        lines += ["", "Edges that force the order: " + ", ".join(f"{a}→{b}" for a, b in proposal["forcing_edges"]) + "."]
    return "\n".join(lines)
