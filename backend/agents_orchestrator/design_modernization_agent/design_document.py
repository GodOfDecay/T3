"""The target design as a document: the chat reply, the Orchestrator deliverable, and the
Word/PDF export all render from here, so they cannot disagree about what was recorded.

Rendered from the STORED design (`TargetDesignArtifact` as a dict) — never from the model's
retelling of it. Diagrams stay Mermaid source in fenced blocks; the page draws them.
"""
from __future__ import annotations

from typing import Any

PATTERN_LABEL = {
    "in_place_upgrade": "in-place upgrade", "strangler_fig": "strangler fig",
    "branch_by_abstraction": "branch by abstraction", "parallel_run": "parallel run",
    "rewrite": "rewrite", "replatform": "replatform", "retire": "retire", "keep": "keep",
}
TIER_LABEL = {"mechanical": "mechanical", "llm_assisted": "LLM-assisted", "manual": "manual-only"}


def _cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def patterns_text(patterns: list[str]) -> str:
    return " + ".join(PATTERN_LABEL.get(p, p) for p in patterns or [])


def headline(design: dict) -> str:
    """"5 modules: 2 in-place upgrade, …; 4 frozen contracts; 7 traps; 8 ADRs"."""
    counts: dict[str, int] = {}
    for m in design.get("modules") or []:
        key = patterns_text(m.get("patterns") or [])
        counts[key] = counts.get(key, 0) + 1
    mods = ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    n = len(design.get("modules") or [])
    return (f"{n} module{'s' if n != 1 else ''}: {mods}; {len(design.get('frozen_contracts') or [])} frozen "
            f"contracts; {len(design.get('traps') or [])} traps; {len(design.get('adrs') or [])} ADRs")


def design_markdown(design: dict) -> str:
    system = design.get("system_name") or "the legacy system"
    sources = design.get("sources") or {}
    brief, assessment = sources.get("brief") or {}, sources.get("assessment") or {}
    lines = [f"# Target Architecture — {system}", ""]
    built = []
    if brief.get("version"):
        built.append(f"migration-intent brief v{brief['version']} ({_status(brief.get('status'))})")
    if assessment.get("version"):
        commit = f", commit `{str(assessment.get('commit') or '')[:10]}`" if assessment.get("commit") else ""
        built.append(f"assessment v{assessment['version']} ({_status(assessment.get('status'))}{commit})")
    if built:
        lines += [f"Built from {' and '.join(built)}.", ""]
    lines += ["## Summary", "", design.get("summary") or "", "", f"**{headline(design)}.**", ""]

    lines += ["## Target per part of the system", "", "| Part | Today | Target | Modules |", "|---|---|---|---|"]
    for layer in design.get("layers") or []:
        lines.append(f"| {_cell(layer.get('layer'))} | {_cell(layer.get('today'))} | {_cell(layer.get('target'))} | "
                     f"{_cell(', '.join(layer.get('modules') or []))} |")

    paths = design.get("module_paths") or {}
    lines += ["", "## Migration pattern per module", "",
              "| Id | Module | Tier | Risk | Pattern | Why | ADRs | Contracts |", "|---|---|---|---:|---|---|---|---|"]
    for m in design.get("modules") or []:
        name = m.get("module") + (f" (`{paths[m['module_id']]}`)" if paths.get(m.get("module_id")) else "")
        lines.append(f"| {m.get('module_id')} | {_cell(name)} | {TIER_LABEL.get(m.get('tier'), m.get('tier'))} | "
                     f"{m.get('risk_score')} | {patterns_text(m.get('patterns'))} | {_cell(m.get('rationale'))} | "
                     f"{_cell(', '.join(m.get('adr_ids') or []))} | {_cell(', '.join(m.get('contract_ids') or []))} |")

    interop = design.get("interop") or {}
    if any(interop.values()):
        lines += ["", "## How the old and the new coexist", ""]
        for key, label in (("routing", "Routing"), ("data", "Data"), ("shared_libraries", "Shared libraries"),
                           ("jobs", "Scheduled jobs"), ("identity", "Identity and sessions")):
            if interop.get(key):
                lines.append(f"- **{label}:** {interop[key]}")
    if design.get("ordering_constraints"):
        lines += ["", "### Constraints on the order of the move", ""]
        lines += [f"- {c}" for c in design["ordering_constraints"]]

    lines += ["", "## Frozen contracts", ""]
    contracts = design.get("frozen_contracts") or []
    if contracts:
        lines += ["| Id | Contract | Kind | Defined in | Consumers | Proof | Status |", "|---|---|---|---|---|---|---|"]
        for c in contracts:
            status = c.get("status") + (" — the brief: “" + c["brief_item"] + "”" if c.get("brief_item") else "")
            lines.append(f"| {c.get('id')} | {_cell(c.get('name'))} | {c.get('kind')} | `{_cell(c.get('legacy_location'))}` | "
                         f"{_cell(', '.join(c.get('consumers') or []))} | {_cell(c.get('proof'))} | {_cell(status)} |")
    else:
        lines.append("None.")

    dm = design.get("data_migration")
    if dm:
        lines += ["", "## Data migration", "", f"- **From:** {dm.get('source')}", f"- **To:** {dm.get('target')}",
                  f"- **Method:** {dm.get('method')}", f"- **Cutover:** {dm.get('cutover')}"]
        if dm.get("behaviour_changes"):
            lines.append("- **Engine behaviour changes:** " + "; ".join(dm["behaviour_changes"]))

    if design.get("nfr"):
        lines += ["", "## Non-functional targets", "", "| Measure | Target | From |", "|---|---|---|"]
        lines += [f"| {_cell(n.get('measure'))} | {_cell(n.get('target'))} | {n.get('source')} |" for n in design["nfr"]]
    if design.get("security_design"):
        lines += ["", "## Security design", ""] + [f"- {s}" for s in design["security_design"]]

    lines += ["", "## Version traps", ""]
    traps = design.get("traps") or []
    if traps:
        lines += ["| Id | Change | Where it bites | Effect | Modules | Contracts |", "|---|---|---|---|---|---|"]
        for t in traps:
            lines.append(f"| {t.get('id')} | {_cell(t.get('change'))} | `{_cell(t.get('where'))}` | {_cell(t.get('effect'))} | "
                         f"{_cell(', '.join(t.get('affects') or []))} | {_cell(', '.join(t.get('contract_ids') or []))} |")
    else:
        lines.append("None named.")

    lines += ["", "## Architecture decisions", ""]
    for a in design.get("adrs") or []:
        lines += [f"### {a.get('id')} — {a.get('title')}", "", f"**Context.** {a.get('context')}", "",
                  "**Options considered.**", ""]
        lines += [f"- {o}" for o in a.get("options") or []]
        lines += ["", f"**Decision.** {a.get('decision')}", "", f"**Consequences.** {a.get('consequences')}"]
        touches = ", ".join([*(a.get("modules") or []), *(a.get("contracts") or [])])
        if touches:
            lines += ["", f"Touches: {touches}."]
        lines.append("")

    if design.get("departures_from_brief"):
        lines += ["## Departures from the brief", "", "| The brief said | The design says | ADR |", "|---|---|---|"]
        lines += [f"| {_cell(d.get('brief_said'))} | {_cell(d.get('design_says'))} | {d.get('adr_id')} |"
                  for d in design["departures_from_brief"]]
        lines.append("")

    if design.get("resolved_questions") or design.get("open_questions"):
        lines += ["## Questions the code could not answer", ""]
        for q in design.get("resolved_questions") or []:
            lines.append(f"- **{q.get('question')}** — {q.get('answer')} _(from the {q.get('source')})_")
        for q in design.get("open_questions") or []:
            lines.append(f"- **Open:** {q}")
        lines.append("")

    lines += ["## Diagrams", ""]
    for d in design.get("diagrams") or []:
        lines += [f"### {d.get('title')}", "", "```mermaid", d.get("mermaid") or "", "```", ""]

    if design.get("notes"):
        lines += ["## Notes", ""] + [f"- {n}" for n in design["notes"]] + [""]
    lines += ["## Next steps", "",
              "- Get the design signed off: an Architect who did not produce it, or a Project Admin as fallback. "
              "Approval puts every module on the migration ledger as *designed*.",
              "- Then Migration Strategy sequences the modules into waves and turns the contracts and traps into "
              "equivalence criteria."]
    return "\n".join(lines)


def _status(status: Any) -> str:
    return {"published": "approved", "granted": "approved by exception", "draft": "not yet approved"}.get(
        str(status or ""), str(status or "unknown"))
