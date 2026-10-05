"""A module's migration record as a document — the chat reply, the export and the Orchestrator
deliverable all render the STORED record from here, so they cannot disagree."""
from __future__ import annotations

from typing import Any

from agents_orchestrator.development_modernization_agent.record import headline

_OUTCOME = {"ready_for_review": "ready for review", "build_failed": "build failed", "blocked": "blocked"}


def _cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def migration_markdown(r: dict) -> str:
    m = r.get("module") or {}
    lines = [f"# Migration — {r['module_id']} {m.get('name') or ''} (`{r['legacy_module_path']}`)", "",
             f"**{_OUTCOME.get(r.get('outcome'), r.get('outcome'))}** — {headline(r)}.", ""]
    src = r.get("sources") or {}
    built = [f"{label} v{s['version']}" for label, key in (("target design", "design"), ("migration plan", "plan"),
                                                          ("baseline", "baseline")) if (s := src.get(key)) and s.get("version")]
    if built:
        lines += ["Built from " + ", ".join(built) + ".", ""]
    if r.get("outcome") == "blocked":
        lines += ["## What a person must redesign", "", r.get("handoff_note") or "", ""]
        return "\n".join(lines)
    lines += [f"Tier {m.get('tier') or '—'}, patterns {', '.join(m.get('patterns') or []) or '—'}, wave "
              f"{m.get('wave') or '—'}, target {m.get('target_runtime') or '—'}. Branch `{r.get('target_branch') or '—'}` "
              f"from `{r.get('base_branch') or '—'}`, head `{(r.get('head_sha') or '')[:10]}`.", ""]
    b = r.get("build") or {}
    lines += ["## Build and checks", "",
              f"- Build: **{b.get('status')}** after {b.get('rounds')} round(s)"
              + (f" — {_cell(b.get('failing'))[:300]}" if b.get("failing") else "")]
    for kind in ("tests", "lint"):
        res = r.get(kind) or {}
        lines.append(f"- {kind.capitalize()}: {res.get('status', 'not run')}" + (f" — {res['note']}" if res.get("note") else ""))
    p = r.get("preview")
    if p:
        lines.append(f"- Equivalence preview (a hint, not the verdict): {p.get('headline')}")
    if r.get("recipes"):
        lines += ["", "## Recipes", "", "| Tool | Version | Arguments | Files |", "|---|---|---|---:|"]
        lines += [f"| {x['tool']} | {_cell(x['version'])} | {_cell(x.get('args'))} | {len(x.get('files') or [])} |"
                  for x in r["recipes"]]
    lines += ["", "## Legacy → target", "", "| Legacy file | Disposition | Target / reason |", "|---|---|---|"]
    lines += [f"| {e['legacy_path']} | {e['disposition']} | {_cell(e.get('target_path') or e.get('reason'))} |"
              for e in r.get("file_map") or []]
    if r.get("llm_rewritten"):
        lines += ["", "## Rewritten by hand", ""] + [f"- `{x['file']}`: {x['reason']}" for x in r["llm_rewritten"]]
    if r.get("traps_handled"):
        lines += ["", "## Traps handled", ""] + [f"- {t}: {w}" for t, w in sorted(r["traps_handled"].items())]
    if r.get("commits"):
        lines += ["", "## Commits", ""] + [f"- `{c['sha'][:10]}` {c['subject']}" for c in r["commits"]]
    if r.get("vault_references"):
        lines += ["", "## Secrets to provision", ""] + [f"- {v}" for v in r["vault_references"]]
    if r.get("manual_follow_ups"):
        lines += ["", "## Left for a person", ""] + [f"- {f}" for f in r["manual_follow_ups"]]
    if r.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]]
    lines += ["", "Accepting this version (a Developer who did not record it, or a Project Admin) lets the branch be "
                  "pushed and the pull request opened; Migration Review and Security review it."]
    return "\n".join(lines)
