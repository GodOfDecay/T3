"""The migration plan as a document — the chat reply, the Orchestrator deliverable and the Word/PDF
export all render the STORED plan from here, so they cannot disagree about what was recorded."""
from __future__ import annotations

from typing import Any

COMPARISON = {"exact": "exact", "byte_identical": "byte-identical", "numeric_tolerance": "within a tolerance",
              "schema_equal": "same schema", "set_equal": "same set", "percentile_threshold": "percentile threshold"}


def _cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def headline(plan: dict) -> str:
    waves = [w for w in plan.get("waves") or [] if w.get("id") != "W0"]
    dues = sorted(str(b.get("due")) for b in plan.get("baseline_plan") or [] if b.get("due"))
    last = max((str(w.get("ends")) for w in waves if w.get("ends")), default="")
    parts = [f"foundation plus {len(waves)} wave{'s' if len(waves) != 1 else ''}",
             f"{len(plan.get('equivalence_criteria') or [])} equivalence criteria"]
    if dues:
        parts.append(f"last baseline due {dues[-1]}")
    if last:
        parts.append(f"last wave ends {last}")
    open_conflicts = [c for c in plan.get("calendar_conflicts") or [] if not (c.get("resolution") or "").strip()]
    if open_conflicts:
        parts.append(f"{len(open_conflicts)} calendar conflict{'s' if len(open_conflicts) != 1 else ''} open")
    return ", ".join(parts)


def strategy_markdown(plan: dict) -> str:
    system = plan.get("system_name") or "the legacy system"
    lines = [f"# Migration Strategy — {system}", ""]
    src = plan.get("sources") or {}
    built = [f"{label} v{s['version']} ({_status(s.get('status'))})" for label, key in
             (("brief", "brief"), ("assessment", "assessment"), ("target design", "design"))
             if (s := src.get(key)) and s.get("version")]
    if built:
        lines += ["Built from " + ", ".join(built) + ".", ""]
    lines += ["## Summary", "", plan.get("summary") or "", "", f"**{headline(plan)}.**", ""]

    lines += ["## Waves", "", "| Wave | Modules | Dates | Cutover window | Parallel run | Why in this order |",
              "|---|---|---|---|---|---|"]
    for w in plan.get("waves") or []:
        pr = w.get("parallel_run") or {}
        run = f"{pr.get('period')} ({pr.get('system_of_record')} stays the system of record)" if pr.get("required") else "—"
        mods = ", ".join(f"{m} ({'+'.join((w.get('patterns') or {}).get(m, []))})" for m in w.get("modules") or [])
        lines.append(f"| {w['id']} {_cell(w.get('name'))} | {_cell(mods)} | {w.get('starts')} → {w.get('ends')} "
                     f"({w.get('date_status')}) | {_cell(w.get('cutover_window'))} | {_cell(run)} | {_cell(w.get('order_reason'))} |")
    for w in plan.get("waves") or []:
        rb = w.get("rollback") or {}
        lines += ["", f"### {w['id']} — {w.get('name')}", "",
                  f"- **Entry:** {'; '.join(w.get('entry_criteria') or []) or '—'}",
                  f"- **Exit:** {'; '.join(w.get('exit_criteria') or [])}",
                  f"- **Rollback:** when {rb.get('trigger')}, {rb.get('method')}"
                  + (f" (within {rb['max_time']})" if rb.get("max_time") else ""),
                  f"- **Owner:** {w.get('owner') or '—'}"]
    if plan.get("order_exceptions"):
        lines += ["", "### Moved before what they depend on (the design allows it)", ""]
        lines += [f"- {x['module_id']} before {x['depends_on']}: {x['reason']} ({x['adr_id']})"
                  for x in plan["order_exceptions"]]

    lines += ["", "## Equivalence criteria", "",
              "| Id | Module | Protects | Observable | Input set | Comparison | Normalization |",
              "|---|---|---|---|---|---|---|"]
    for c in plan.get("equivalence_criteria") or []:
        protects = ", ".join([*(c.get("protects") or []), *(f"“{m}”" for m in c.get("protects_measures") or [])])
        norm = "; ".join(f"{r['field']}: {r['rule']} ({r['reason']})" for r in c.get("normalization") or []) or "none"
        comp = COMPARISON.get(c.get("comparison"), c.get("comparison")) + (f" — {c['threshold']}" if c.get("threshold") else "")
        lines.append(f"| {c['id']} | {c['module_id']} | {_cell(protects)} | {_cell(c.get('observable'))} | "
                     f"{_cell(c.get('input_set'))} | {_cell(comp)} | {_cell(norm)} |")

    lines += ["", "## Baseline plan (recorded from the legacy system before anything changes)", "",
              "| Criterion | Inputs | Environment | Data source | Masking | Due |", "|---|---|---|---|---|---|"]
    lines += [f"| {b['ec_id']} | {_cell(b.get('inputs'))} | {_cell(b.get('environment'))} | {_cell(b.get('data_source'))} | "
              f"{_cell(b.get('masking'))} | {b.get('due')} |" for b in plan.get("baseline_plan") or []]

    fp = plan.get("freeze_policy") or {}
    lines += ["", "## Legacy change freeze", "", f"From {fp.get('from')}: {fp.get('allowed')}. {fp.get('carry_forward')}"]
    if plan.get("critical_path"):
        lines += ["", "## Critical path", ""] + [f"{i}. {s}" for i, s in enumerate(plan["critical_path"], 1)]
    if plan.get("calendar_conflicts"):
        lines += ["", "## Calendar conflicts", "", "| Conflict | Impact | Options | Resolution |", "|---|---|---|---|"]
        lines += [f"| {_cell(c.get('conflict'))} | {_cell(c.get('impact'))} | {_cell('; '.join(c.get('options') or []))} | "
                  f"{_cell(c.get('resolution') or 'OPEN')} |" for c in plan["calendar_conflicts"]]
    raid = plan.get("raid") or {}
    if any(raid.get(k) for k in ("risks", "assumptions", "issues", "dependencies")):
        lines += ["", "## RAID", ""]
        lines += [f"- **Risk:** {r['risk']} — evidence: {r['evidence']}; mitigation: {r['mitigation']}" for r in raid.get("risks") or []]
        lines += [f"- **Assumption:** {a}" for a in raid.get("assumptions") or []]
        lines += [f"- **Issue:** {i}" for i in raid.get("issues") or []]
        lines += [f"- **Dependency:** {d}" for d in raid.get("dependencies") or []]
    lines += ["", "## Effort (an estimate, not a quote)", "", "| Wave | Band | Basis |", "|---|---|---|"]
    lines += [f"| {e['wave']} | {_cell(e.get('band'))} | {_cell(e.get('basis'))} |" for e in plan.get("effort") or []]
    if plan.get("budget_fit"):
        lines += ["", f"**Budget:** {plan['budget_fit']}"]
    if plan.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in plan["notes"]]
    lines += ["", "## Next steps", "",
              "- Sign-off: an Architect who did not produce it, or a Project Admin as fallback. Approval places every "
              "planned module on the migration ledger as *sequenced*, with its wave and criteria.",
              "- Write the waves to the board (one Feature per wave, one item per module) — on your confirmation.",
              "- Then Equivalence Testing records the baselines before Migration Development starts the first wave."]
    return "\n".join(lines)


def _status(status: Any) -> str:
    return {"published": "approved", "granted": "approved by exception", "draft": "not yet approved"}.get(
        str(status or ""), str(status or "unknown"))
