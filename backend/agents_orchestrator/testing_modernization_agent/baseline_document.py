"""The baseline as a document — the chat reply, the Orchestrator deliverable and the Word/PDF export all
render the STORED baseline from here, so they cannot disagree. Counts, hashes, field names and masked
shapes only: a recording is never rendered."""
from __future__ import annotations

from typing import Any


def _cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def _status(s: Any) -> str:
    return {"published": "approved", "granted": "approved by exception"}.get(str(s), "not yet approved")


def headline(b: dict) -> str:
    bls = b.get("baselines") or []
    modules = sorted({x["module_id"] for x in bls} - {"all"})
    parts = [f"{len(bls)} baseline{'s' if len(bls) != 1 else ''}",
             f"{len({e for x in bls for e in x.get('ec_ids') or []})} criteria recorded",
             f"modules {', '.join(modules) or 'none'}"]
    if b.get("rule_proposals"):
        parts.append(f"{len(b['rule_proposals'])} rule proposal{'s' if len(b['rule_proposals']) != 1 else ''} to Migration Strategy")
    if b.get("not_captured"):
        parts.append(f"{len(b['not_captured'])} not captured")
    return ", ".join(parts)


def baseline_markdown(b: dict) -> str:
    system = b.get("system_name") or "the legacy system"
    cap = b.get("capture") or {}
    src = b.get("sources") or {}
    lines = [f"# Baseline — {system}", ""]
    built = [f"{label} v{s['version']} ({_status(s.get('status'))})" for label, key in
             (("migration plan", "plan"), ("target design", "design")) if (s := src.get(key)) and s.get("version")]
    if built:
        lines += ["Built from " + ", ".join(built) + ".", ""]
    lines += [f"**{headline(b)}.**", "",
              f"Capture `{cap.get('id')}`: the legacy system run twice in an isolated sandbox (no internet, synthetic "
              f"data), commit `{str(cap.get('commit') or '')[:10]}`, image `{str(cap.get('imageId') or '')[:19]}`, "
              f"{cap.get('startedAt') or ''} → {cap.get('finishedAt') or ''}.", ""]
    lines += ["## Baselines", "", "| Id | Module | Criteria | Recorded | Hash (sha256) | Region | Varies between runs |",
              "|---|---|---|---:|---|---|---|"]
    for x in b.get("baselines") or []:
        lines.append(f"| {x['id']} | {x['module_id']} | {', '.join(x['ec_ids'])} | {x['count']} {x['unit']} | "
                     f"`{x['sha256'][:16]}…` | {x['region']} | {_cell(', '.join(x.get('noise_fields') or []))} |")
    lines += ["", "## Scenarios", "", "| Scenario | Kind | Cases | What it does |", "|---|---|---:|---|"]
    for s in b.get("scenarios") or []:
        lines.append(f"| {s['id']} | {s['kind']} | {_cell(s.get('cases'))} | {_cell(s.get('describes'))} |")
    lines += ["", "## Noise floor", "",
              "Fields that differed between two runs of the UNCHANGED legacy system — they cannot be compared as "
              "they are.", "", "| Criterion | Varying fields | Covered by a rule |", "|---|---|---|"]
    for n in b.get("noise") or []:
        lines.append(f"| {n['ec_id']} | {_cell(', '.join(n.get('varying_fields') or []) or 'none')} | "
                     f"{_cell(', '.join(n.get('covered_by_rule') or []))} |")
    if b.get("rule_proposals"):
        lines += ["", "## Proposed to Migration Strategy", "",
                  "Normalization rules this agent PROPOSES (it never applies one). The criterion stays open until "
                  "the plan is revised.", "", "| Criterion | Field | Proposed rule | Evidence |", "|---|---|---|---|"]
        lines += [f"| {p['ec_id']} | {p['field']} | {_cell(p['rule'])} | {_cell(p['evidence'])} |"
                  for p in b["rule_proposals"]]
    if b.get("not_captured"):
        lines += ["", "## Not captured in Baseline mode", ""]
        lines += [f"- {n['ec_id']}: {n['reason']}" for n in b["not_captured"]]
    if b.get("stubs"):
        lines += ["", f"External services answered by stubs: {', '.join(b['stubs'])}."]
    if b.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in b["notes"]]
    lines += ["", "Accepting this version (QA who did not record it, or a Project Admin) moves each baselined module "
                  "to **baselined** on the migration ledger — Migration Development starts from it."]
    return "\n".join(lines)
