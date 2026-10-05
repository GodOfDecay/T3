"""The reading tools Migration Review and Security share (Phase I): one module's accepted migration, both
sides of it, and the design and plan around it. Every file opened is noted (`review_checkout.note_read`)
under the asking stage, so a submitted review can only cite files the run opened (I5).

    tools = make_review_read_tools("code_review_modernization", "Migration Review")
"""
from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

from agents_orchestrator.modernization_common import review_checkout as RC

logger = logging.getLogger(__name__)

DESIGN, PLAN = "design_modernization", "strategy"
_MAX_LINES = 400


def _approved(item) -> bool:
    return item.version is not None and item.status in ("published", "granted")


async def module_context(module_id: str) -> tuple[Optional[dict], str]:
    """The module's slice of the design and the plan: contracts, traps, ADRs, criteria, and their labels."""
    from agents_orchestrator.modernization_common.inputs import missing_line, read_inputs  # noqa: PLC0415

    ins = await read_inputs([DESIGN, PLAN])
    for stage in (DESIGN, PLAN):
        if ins[stage].packet is None:
            return None, missing_line(ins[stage])
    design, plan = ins[DESIGN].stored or {}, ins[PLAN].stored or {}
    dmod = next((m for m in design.get("modules") or [] if m.get("module_id") == module_id), None)
    if dmod is None:
        return None, f"{module_id} is not in {ins[DESIGN].label}."
    contract_ids = dmod.get("contract_ids") or []
    adr_ids = dmod.get("adr_ids") or []
    return {
        "module_id": module_id, "name": dmod.get("module"), "tier": dmod.get("tier"),
        "patterns": dmod.get("patterns") or [], "rationale": dmod.get("rationale"),
        "contracts": [c for c in design.get("frozen_contracts") or [] if c.get("id") in contract_ids],
        "traps": [t for t in design.get("traps") or [] if module_id in (t.get("affects") or [])],
        "adrs": [a for a in design.get("adrs") or [] if a.get("id") in adr_ids or module_id in (a.get("modules") or [])],
        "criteria": [c for c in plan.get("equivalence_criteria") or [] if c.get("module_id") in (module_id, "all")],
        "layers": [{"layer": la.get("layer"), "target": la.get("target")} for la in design.get("layers") or []
                   if module_id in (la.get("modules") or [])],
        "waves": [{"id": w.get("id"), "starts": w.get("starts"), "ends": w.get("ends")} for w in plan.get("waves") or []],
        "system_name": design.get("system_name") or "",
        "design_label": ins[DESIGN].label, "plan_label": ins[PLAN].label,
        "sources": {"design": {"version": ins[DESIGN].version, "status": ins[DESIGN].status},
                    "plan": {"version": ins[PLAN].version, "status": ins[PLAN].status}},
        "approved": _approved(ins[DESIGN]) and _approved(ins[PLAN]),
    }, ""


def counterpart_map(record: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    """(target → legacy, legacy → [targets]) from the record's file map."""
    to_legacy, to_target = {}, {}
    for e in record.get("file_map") or []:
        if e.get("disposition") in ("mapped", "merged") and e.get("target_path"):
            to_legacy[e["target_path"]] = e["legacy_path"]
            to_target.setdefault(e["legacy_path"], []).append(e["target_path"])
    return to_legacy, to_target


def _numbered(text: str, start: int, count: int) -> tuple[str, int]:
    rows = text.splitlines()
    start = max(1, start)
    chunk = rows[start - 1:start - 1 + max(1, min(count, _MAX_LINES))]
    body = "\n".join(f"{start + i:>5}  {line}" for i, line in enumerate(chunk))
    return body, len(rows)


def _read(path) -> Optional[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def migration_markdown(mig: RC.Migration, ctx: dict) -> str:
    r = mig.record
    lines = [f"# {mig.module_id} {ctx.get('name') or ''} — `{mig.module_path}/`", "",
             f"Migration record v{mig.version} ({'accepted' if mig.status == 'published' else 'accepted by exception'}), "
             f"branch `{mig.branch}` at `{mig.head[:10]}`; pull request {r.get('pr_url') or (mig.ledger.get('prUrl') or 'not opened')}.",
             f"Ledger: **{mig.ledger.get('state') or 'unknown'}**"
             + (f", review {mig.ledger.get('reviewVerdict')}" if mig.ledger.get("reviewVerdict") else "")
             + (f", security {mig.ledger.get('securityVerdict')}" if mig.ledger.get("securityVerdict") else "") + ".",
             f"Legacy code at `{(mig.legacy_commit or 'not pulled')[:10]}`. From {ctx['design_label']} and {ctx['plan_label']}.",
             f"Tier {ctx.get('tier') or '—'}, patterns {', '.join(ctx.get('patterns') or []) or '—'}; "
             + "; ".join(f"{la['layer']} → {la['target']}" for la in ctx.get("layers") or []), "",
             f"Build {(r.get('build') or {}).get('status')} after {(r.get('build') or {}).get('rounds')} round(s); "
             f"tests {(r.get('tests') or {}).get('status', 'not run')}; lint {(r.get('lint') or {}).get('status', 'not run')}."]
    if r.get("recipes"):
        lines.append("Recipes: " + "; ".join(f"{x['tool']} {x['version']}" for x in r["recipes"]))
    lines += ["", "## File map (legacy → target)"] + [
        f"- `{e['legacy_path']}` {e['disposition']} → {('`' + e['target_path'] + '`') if e.get('target_path') else e.get('reason') or ''}"
        for e in r.get("file_map") or []]
    if r.get("llm_rewritten"):
        lines += ["", "## Rewritten by hand"] + [f"- `{x['file']}`: {x['reason']}" for x in r["llm_rewritten"]]
    if r.get("traps_handled"):
        lines += ["", "## Traps the developer says are handled"] + [f"- {k}: {v}" for k, v in sorted(r["traps_handled"].items())]
    if r.get("changed_files"):
        lines += ["", f"Changed files: {', '.join(r['changed_files'][:40])}"]
    lines += ["", "## Frozen contracts"] + ([
        f"- {c['id']} {c.get('name')} ({c.get('kind')}) at `{c.get('legacy_location') or ''}`" for c in ctx["contracts"]]
        or ["- none on this module"])
    lines += ["", "## Traps"] + ([f"- {t['id']} {t.get('change')}: {t.get('effect')} ({t.get('where') or ''})"
                                  for t in ctx["traps"]] or ["- none on this module"])
    lines += ["", "## Equivalence criteria"] + ([f"- {c['id']} {c.get('observable')} ({c.get('comparison')})"
                                                 for c in ctx["criteria"]] or ["- none for this module"])
    if ctx["adrs"]:
        lines += ["", "## ADRs"] + [f"- {a['id']} {a.get('title') or ''}: {(a.get('decision') or '')[:200]}" for a in ctx["adrs"]]
    if r.get("vault_references"):
        lines += ["", "Vault references: " + ", ".join(r["vault_references"])]
    if not ctx["approved"]:
        lines += ["", "Note: the design or the plan read here is not approved yet."]
    return "\n".join(lines)


def make_review_read_tools(stage: str, label: str) -> list:
    """read_module_migration, list_migration_files, read_migrated_file, read_legacy_counterpart for `stage`."""

    @tool
    async def read_module_migration(module_id: str) -> str:
        """The module's ACCEPTED migration: the record (file map, recipes, rewrites, traps handled, build), the
        branch and head reviewed, the pull request, the ledger state, and the module's frozen contracts (CT-xx),
        traps (TR-xx), equivalence criteria (EC-xx) and ADRs. Call it first."""
        ctx, why = await module_context(module_id)
        if ctx is None:
            return why
        mig, why = await RC.open_migration(stage, module_id, label)
        if mig is None:
            return why
        return migration_markdown(mig, ctx)

    @tool
    async def list_migration_files(module_id: str) -> str:
        """Every file of the module on both sides, paired through the file map: target file ↔ legacy counterpart."""
        mig, why = await RC.open_migration(stage, module_id, label)
        if mig is None:
            return why
        to_legacy, _to_target = counterpart_map(mig.record)
        target, legacy = mig.target_paths(), mig.legacy_module_files()
        lines = [f"Target at `{mig.head[:10]}` ({len(target)} files) ↔ legacy at `{(mig.legacy_commit or 'not pulled')[:10]}` "
                 f"({len(legacy)} files):", "", "| Target | Legacy counterpart |", "|---|---|"]
        lines += [f"| `{t}` | {('`' + to_legacy[t] + '`') if t in to_legacy else '—'} |" for t in target]
        unmapped = sorted(set(legacy) - set(to_legacy.values()))
        if unmapped:
            lines += ["", "Legacy files with no target counterpart: " + ", ".join(f"`{u}`" for u in unmapped)]
        if mig.legacy is None:
            lines += ["", "The legacy code is not pulled for this stage: pull it to read the counterparts."]
        return "\n".join(lines)

    @tool
    async def read_migrated_file(module_id: str, path: str, start_line: int = 1, max_lines: int = 300) -> str:
        """Read a file of the migrated module on the TARGET, at the head that was accepted (numbered lines)."""
        mig, why = await RC.open_migration(stage, module_id, label)
        if mig is None:
            return why
        p = RC.resolve(mig.target, path)
        text = _read(p) if p else None
        if text is None:
            return f"{path} is not a readable file of the target at {mig.head[:10]}."
        rel = p.relative_to(mig.target.resolve()).as_posix()
        RC.note_read(stage, module_id, "target", rel)
        body, total = _numbered(text, start_line, max_lines)
        return f"`{rel}` (target, {total} lines)\n{body}"

    @tool
    async def read_legacy_counterpart(module_id: str, path: str, start_line: int = 1, max_lines: int = 300) -> str:
        """Read the LEGACY file a target file came from (through the file map), or a legacy path directly."""
        mig, why = await RC.open_migration(stage, module_id, label, clone=False)
        if mig is None:
            return why
        if mig.legacy is None:
            return "The legacy code is not pulled for this stage: pull it first."
        to_legacy, _ = counterpart_map(mig.record)
        rel = to_legacy.get(path.strip().lstrip("/"), path)
        p = RC.resolve(mig.legacy, rel)
        text = _read(p) if p else None
        if text is None:
            return f"{rel} is not a readable legacy file (the file map has no counterpart for {path}, or it is binary)."
        rel = p.relative_to(mig.legacy.resolve()).as_posix()
        RC.note_read(stage, module_id, "legacy", rel)
        body, total = _numbered(text, start_line, max_lines)
        return f"`{rel}` (legacy, {total} lines)\n{body}"

    return [read_module_migration, list_migration_files, read_migrated_file, read_legacy_counterpart]
