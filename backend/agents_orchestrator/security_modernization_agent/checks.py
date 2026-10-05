"""What a Track 3 security report must prove before it is saved (Phase I, I10). Pure.

The packet (`SecurityPayload`) computes the sign-off policy. Here: the report cannot leave out what the
tools found. Every critical or high hit on the target is a finding, matched by CVE + package, or by file
for code and secrets; its origin is the one `compare.diff_findings` computed; every carried-over secret
is a critical secret finding; every frozen HTTP contract has an authz line, and one the evidence calls
weaker is not "same" without a note.
"""
from __future__ import annotations

_BLOCKING = {"critical", "high"}


def _matches(finding: dict, hit: dict) -> bool:
    if hit["tool"] == "trivy":
        return bool(hit.get("cve")) and finding.get("cve") == hit["cve"] and \
            (finding.get("package") or "").lower() == (hit.get("package") or "").lower()
    if hit["tool"] == "gitleaks":
        return bool(finding.get("is_secret")) and finding.get("file") == hit.get("file")
    return finding.get("file") == hit.get("file") and not finding.get("cve")


def check(*, report: dict, target_hits: list[dict], carryover: list[dict], http_contracts: list[str],
          authz: dict[str, dict], wave_ends: str = "") -> list[str]:
    problems: list[str] = []
    findings = report.get("findings") or []
    if report.get("verdict") == "CONDITIONAL" and wave_ends:
        late = [f["id"] for f in findings if f.get("remediation_due") and str(f["remediation_due"]) > wave_ends]
        if late:
            problems.append(f"CONDITIONAL needs every remediation inside the module's wave (it ends {wave_ends}); "
                            f"{', '.join(late)} fall after it.")
    for hit in target_hits:
        if hit.get("severity") not in _BLOCKING:
            continue
        what = (f"{hit['cve']} in {hit.get('package')}" if hit["tool"] == "trivy"
                else f"{hit.get('title')} at {hit.get('file')}:{hit.get('line') or ''}".rstrip(":"))
        found = [f for f in findings if _matches(f, hit)]
        if not found:
            problems.append(f"The {hit['severity']} hit {what} ({hit['tool']}) is not in the findings. List it — at the "
                            "severity you can justify, with why if it is a false positive.")
        elif not any(f.get("origin") == hit.get("origin") for f in found):
            problems.append(f"{what} is {hit.get('origin', '').replace('_', ' ')} (the legacy scan "
                            f"{'has' if hit.get('origin') == 'carried_over' else 'does not have'} it); its finding says otherwise.")
    for c in carryover:
        if not any(f.get("is_secret") and f.get("origin") == "carried_over" and f.get("file") == c["file"]
                   and f.get("severity") == "critical" for f in findings):
            problems.append(f"A legacy secret is in the target at {c['file']}:{c['line']} (from {c['legacy_file']}). It is a "
                            "critical, carried-over secret finding (is_secret true): rotate and remove.")
    stated = {a.get("ct_id"): a for a in report.get("contract_authz") or []}
    if missing := sorted(set(http_contracts) - set(stated)):
        problems.append("Every frozen HTTP contract needs an authorization check; missing: " + ", ".join(missing) + ".")
    for ct, ev in authz.items():
        a = stated.get(ct)
        if a and ev.get("suggested") == "weaker" and a.get("status") != "weaker" and not (a.get("note") or "").strip():
            problems.append(f"The evidence says {ct}'s authorization is weaker ({ev.get('reason')}); say why it is not, "
                            "in the note, or mark it weaker.")
    return problems
