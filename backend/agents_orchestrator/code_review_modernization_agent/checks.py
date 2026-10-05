"""What a migration review must prove before it is saved (Phase I, I5/I6). Pure: the submit tool gathers
the facts (the module's design and plan slice, the accepted record, the files the run opened, the API
diff) and these functions judge them. Each problem is a sentence the agent passes on.

The packet (`ReviewPayload`) already enforces the merge-recommendation rules. Here: completeness (every
contract, trap, criterion and legacy file of the module answered), honesty (files cited were opened),
and the deterministic diff (a contract whose file changed in a contract-bearing way is not "unchanged"
without saying why).
"""
from __future__ import annotations

#: Surface kinds that ARE a contract when they change (an import or a helper's name is not).
CONTRACT_KINDS = {"http_path", "http_method", "status", "sql", "encoding", "file_write"}
_COMPARING = {"contract_drift", "behaviour_change", "carried_over", "trap_unhandled"}


def check(*, review: dict, ctx: dict, record: dict, opened: dict[str, list[str]], surface: dict,
          legacy_files: list[str]) -> list[str]:
    problems: list[str] = []
    contracts = {c["id"] for c in ctx.get("contracts") or []}
    traps = {t["id"] for t in ctx.get("traps") or []}
    criteria = {c["id"] for c in ctx.get("criteria") or []}
    cc = {c.get("ct_id"): c for c in review.get("contract_check") or []}
    tc = {t.get("tr_id") for t in review.get("trap_check") or []}
    ec = {e.get("ec_id") for e in review.get("equivalence_coverage") or []}
    tr = {t.get("legacy_path") for t in review.get("traceability") or []}

    for label, need, have in (("frozen contract", contracts, set(cc)), ("trap", traps, tc), ("equivalence criterion", criteria, ec)):
        if missing := sorted(need - have):
            problems.append(f"Every {label} of the module needs a check; missing: {', '.join(missing)}.")
        if unknown := sorted(x for x in have - need if x):
            problems.append(f"The review checks {label}s the module does not have: {', '.join(unknown)}.")
    if missing := sorted(set(legacy_files) - tr):
        problems.append("Traceability must cover every legacy file of the module; missing: " + ", ".join(missing[:15]) + ".")
    if extra := sorted(p for p in tr - set(legacy_files) if p):
        problems.append("Traceability lists files the legacy module does not have: " + ", ".join(extra[:10]) + ".")

    target_read, legacy_read = set(opened.get("target") or []), set(opened.get("legacy") or [])
    if not target_read:
        problems.append("No migrated file was opened: read the code before reviewing it.")
    for f in review.get("findings") or []:
        if f.get("file") and f["file"] not in target_read:
            problems.append(f"{f.get('id')} cites {f['file']}, which this review did not open. Open it, or drop the finding.")
        if f.get("legacy_file") and f["legacy_file"] not in legacy_read:
            problems.append(f"{f.get('id')} cites legacy {f['legacy_file']}, which this review did not open.")
        if f.get("category") in _COMPARING and not f.get("legacy_file"):
            problems.append(f"{f.get('id')} compares the two sides ({f.get('category')}); cite the legacy file and line too.")
    for t in review.get("trap_check") or []:
        if t.get("status") == "handled" and not (t.get("where") or "").strip():
            problems.append(f"{t.get('tr_id')} is handled — say where (file:line).")

    for ct, changes in (surface.get("contracts") or {}).items():
        bearing = [c for c in changes if c.get("kind") in CONTRACT_KINDS]
        entry = cc.get(ct)
        if bearing and entry and entry.get("status") == "unchanged" and not (entry.get("note") or "").strip():
            problems.append(f"{ct} is marked unchanged, but its file changed: " + "; ".join(
                f"{c['change']} {c['kind']} `{c['name'][:50]}`" for c in bearing[:4])
                + ". Explain in the note why that is not a change to the contract, or mark it changed.")
    return problems
