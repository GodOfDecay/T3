"""The security report as a document (Phase I): the page's "Download" and the export tool, one renderer."""
from __future__ import annotations

_SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def origin_counts(a: dict) -> dict[str, int]:
    fs = a.get("findings") or []
    return {"introduced": sum(1 for f in fs if f.get("origin") == "introduced"),
            "carried_over": sum(1 for f in fs if f.get("origin") == "carried_over"),
            "fixed": len(a.get("fixed_from_legacy") or [])}


def security_markdown(a: dict) -> str:
    c = origin_counts(a)
    sb = a.get("sbom") or {}
    lines = [f"# Security report — {a['module_id']} {(a.get('module') or {}).get('name') or ''}", "",
             f"**Verdict: {a['verdict']}** · pull request {a['pr']}",
             f"Scanned head `{(a.get('head_sha') or '')[:10]}` (migration record v{a.get('migration_version')}) against the "
             f"legacy code at `{(a.get('legacy_commit') or '')[:10]}`"
             + (" (legacy scan from the cache)." if a.get("legacy_cached") else "."),
             f"{c['introduced']} introduced, {c['carried_over']} carried over, {c['fixed']} fixed by the migration.", "",
             a.get("rationale") or "", "", "## Scans", "| Scanner | Version | Status |", "|---|---|---|"]
    for t, status in (a.get("scans") or {}).items():
        lines.append(f"| {t} | {(a.get('scanner_versions') or {}).get(t, '')} | {status.replace('_', ' ')} |")
    comps, vulns = sb.get("components"), sb.get("vulnerabilities")
    lines.append(f"\nSBOM: {'not generated' if comps is None else f'{comps} components'}; dependency vulnerabilities: "
                 f"{'not scanned' if vulns is None else vulns}.")
    fs = sorted(a.get("findings") or [], key=lambda f: (_SEV.get(f.get("severity"), 9), f.get("id")))
    if fs:
        lines += ["", "## Findings", "| Id | Severity | Origin | Finding | Where | Reachable | Remediation |",
                  "|---|---|---|---|---|---|---|"]
        for f in fs:
            what = f["title"] + (f" ({f['cve']}, {f.get('package')})" if f.get("cve") else "") + (" — SECRET" if f.get("is_secret") else "")
            reach = {True: "yes", False: "no"}.get(f.get("reachable"), "unknown")
            rem = (f.get("remediation_plan") or "") + (f" by {f['remediation_due']}" if f.get("remediation_due") else "")
            lines.append(f"| {f['id']} | {f['severity']} | {f['origin'].replace('_', ' ')} | {what} | "
                         f"{f.get('file') or f.get('legacy_ref') or ''} | {reach} | {rem or '—'} |")
    if a.get("fixed_from_legacy"):
        lines += ["", "## Fixed by the migration"] + [f"- {x['title']} ({x['legacy_ref']})" for x in a["fixed_from_legacy"]]
    if a.get("contract_authz"):
        lines += ["", "## Contract authorization"] + [f"- {x['ct_id']}: **{x['status']}** {x.get('note') or ''}".rstrip()
                                                       for x in a["contract_authz"]]
    if a.get("secret_carryover"):
        lines += ["", "## Legacy secrets in the target (rotate and remove)"] + [
            f"- {h['file']}:{h['line']} (from {h['legacy_file']})" for h in a["secret_carryover"]]
    return "\n".join(lines)
