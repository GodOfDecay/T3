"""The migration review as a document (Phase I): the page's "Download" and the export tool, one renderer."""
from __future__ import annotations

from agents_orchestrator.code_review_modernization_agent.analysis import SEVERITY_ORDER

_REC = {"approve": "Approve", "request_changes": "Request changes", "needs_discussion": "Needs discussion"}


def severity_counts(findings: list[dict]) -> dict[str, int]:
    return {s: sum(1 for f in findings if f.get("severity") == s) for s in SEVERITY_ORDER}


def review_markdown(a: dict) -> str:
    findings = sorted(a.get("findings") or [], key=lambda f: (SEVERITY_ORDER.get(f.get("severity"), 9), f.get("id")))
    counts = severity_counts(findings)
    lines = [f"# Migration review — {a['module_id']} {(a.get('module') or {}).get('name') or ''}", "",
             f"**Recommendation: {_REC.get(a['merge_recommendation'], a['merge_recommendation'])}** · pull request {a['pr']}",
             f"Reviewed head `{(a.get('head_sha') or '')[:10]}` (migration record v{a.get('migration_version')}) against the "
             f"legacy code at `{(a.get('legacy_commit') or '')[:10]}`.",
             "Findings: " + ", ".join(f"{n} {s}" for s, n in counts.items() if n) if findings else "No findings.",
             "", a.get("summary") or ""]
    if findings:
        lines += ["", "## Findings", "| Id | Severity | Category | Target | Legacy | Finding | Recommendation |",
                  "|---|---|---|---|---|---|---|"]
        for f in findings:
            tgt = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
            leg = (f"{f['legacy_file']}:{f['legacy_line']}" if f.get("legacy_line") else f.get("legacy_file")) or "—"
            lines.append(f"| {f['id']} | {f['severity']} | {f['category'].replace('_', ' ')} | {tgt} | {leg} | "
                         f"{f['description']} | {f['recommendation']} |")
    for title, key, idk, extra in (("Frozen contracts", "contract_check", "ct_id", "note"),
                                   ("Traps", "trap_check", "tr_id", "where"),
                                   ("Equivalence criteria", "equivalence_coverage", "ec_id", "note")):
        if a.get(key):
            lines += ["", f"## {title}"] + [f"- {x[idk]}: **{x['status'].replace('_', ' ')}** {x.get(extra) or ''}".rstrip()
                                             for x in a[key]]
    if a.get("traceability"):
        lines += ["", "## Legacy traceability", "| Legacy | Target | Status |", "|---|---|---|"]
        lines += [f"| {t['legacy_path']} | {t.get('target_path') or '—'} | {t['status'].replace('_', ' ')} |"
                  for t in a["traceability"]]
    if a.get("known_debt"):
        lines += ["", "## Known debt carried over"] + [f"- {d['pattern']} — {d['legacy_file']} {d.get('note') or ''}".rstrip()
                                                        for d in a["known_debt"]]
    fr = a.get("files_read") or {}
    lines += ["", f"Files read: {len(fr.get('target') or [])} target, {len(fr.get('legacy') or [])} legacy "
                  "(recorded by the tools as they were opened)."]
    return "\n".join(lines)
