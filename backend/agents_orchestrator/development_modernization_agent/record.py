"""What a module's migration record must prove before it is saved, and the one builder (H9).

Pure — the record tool gathers the facts (the legacy checkout's file list, the branch diff, the
workspace state, the plan) and these functions judge them. Each problem is a sentence the agent passes
on. The research's acceptance checks are here: the file map is COMPLETE, nothing is touched outside the
module, the build is green for a module put up for review — and the build, the recipes and the head
come from the workspace, never from the model's words.
"""
from __future__ import annotations

import re
from typing import Iterable

from agents_orchestrator.development_modernization_agent import rules

_VAULT_RE = re.compile(r"^(?:kv://|vault:|keyvault:|secretsmanager:|\$\{[A-Z0-9_]+\}$|env:[A-Z0-9_]+$)")


def build_result(state: dict) -> dict:
    """The packet's BuildResult from the workspace: the last build's status and the rounds counted."""
    builds = state.get("builds") or []
    if not builds:
        return {"status": "not_run", "rounds": 0, "failing": None}
    last = builds[-1]
    return {"status": "green" if last["ok"] else "red", "rounds": min(len(builds), 5),
            "failing": None if last["ok"] else (last.get("failing") or "the build failed")[:800]}


def check(*, outcome: str, module_path: str, legacy_files: Iterable[str], file_map: list[dict],
          changed: Iterable[str], target_files: Iterable[str], rewritten: list[dict], traps_for_module: Iterable[str],
          traps_handled: dict[str, str], vault_references: list[str], state: dict, pending: Iterable[str],
          secret_hits: dict[str, list[str]]) -> list[str]:
    problems: list[str] = []
    legacy = sorted(legacy_files)
    changed = sorted(changed)
    target = set(target_files)
    if list(pending):
        problems.append("There are uncommitted changes in the workspace. Commit them (build or fix) first: the "
                        "record describes the branch exactly as it will be pushed.")
    if outcome == "blocked":
        if changed:
            problems.append("A blocked (manual-tier) module has no code written, but the branch changes "
                            f"{len(changed)} file(s).")
        return problems
    mapped = {e.get("legacy_path") for e in file_map}
    missing = [f for f in legacy if f not in mapped]
    if missing:
        problems.append("The file map does not cover every legacy file of the module. Missing: "
                        + ", ".join(missing[:15]) + (f" …and {len(missing) - 15} more" if len(missing) > 15 else "")
                        + ". Say for each: mapped (to which target file), merged (into which), or dropped (why).")
    extra = sorted(p for p in mapped if p and p not in set(legacy))
    if extra:
        problems.append("The file map lists files the legacy module does not have: " + ", ".join(extra[:10]) + ".")
    for e in file_map:
        if e.get("disposition") in ("mapped", "merged") and e.get("target_path") and e["target_path"] not in target:
            problems.append(f"{e['legacy_path']} is {e['disposition']} to {e['target_path']}, which the branch "
                            "does not have.")
    outside = rules.out_of_bounds(changed, module_path)
    if outside:
        problems.append("The branch changes files outside this module and the shared build: "
                        + ", ".join(outside[:10]) + ". Revert them (a new commit) before recording.")
    for r in rewritten:
        if r.get("file") not in set(changed):
            problems.append(f"{r.get('file')} is listed as rewritten, but the branch does not change it.")
    for hit_file, kinds in sorted(secret_hits.items()):
        problems.append(f"{hit_file} appears to hold {', '.join(kinds)}. Put a vault reference in its place and "
                        "list it in vault_references; a secret is never copied.")
    for ref in vault_references:
        if not _VAULT_RE.match(str(ref).strip()):
            problems.append(f"{ref!r} is not a vault reference (kv://…, vault:…, ${{NAME}} or env:NAME).")
    unknown = sorted(set(traps_handled) - set(traps_for_module))
    if unknown:
        problems.append("Traps handled that the design does not list for this module: " + ", ".join(unknown) + ".")
    build = build_result(state)
    if outcome == "ready_for_review":
        unhandled = sorted(set(traps_for_module) - set(traps_handled))
        if unhandled:
            problems.append("Every trap the design lists for this module must be handled, with where: "
                            + ", ".join(unhandled) + ".")
        if build["status"] != "green":
            problems.append(f"The last build is {build['status'].replace('_', ' ')}; only a module whose build "
                            "is green goes for review (record it as build_failed after five rounds).")
        for kind in ("tests", "lint"):
            result = state.get(kind)
            if result and result.get("status") == "red":
                problems.append(f"The last {kind} run failed; fix it or record the module as build_failed.")
            if result and state.get("builds") and result.get("head") != state["builds"][-1].get("head"):
                problems.append(f"The {kind} ran on an earlier commit than the last build; run them again.")
        if not state.get("builds") or state["builds"][-1].get("head") != state.get("head"):
            problems.append("The branch changed after the last build; build again before recording.")
    if outcome == "build_failed" and build["status"] != "red":
        problems.append("build_failed records a red build; the last build is " + build["status"].replace("_", " ") + ".")
    return problems


def pr_body(record: dict) -> str:
    """The pull request's description — generated from the record, so it says what the record says."""
    m = record.get("module") or {}
    lines = [f"## Migration of {record['module_id']} {m.get('name') or ''} — `{record['legacy_module_path']}`", "",
             f"Tier **{m.get('tier') or '—'}**, patterns {', '.join(m.get('patterns') or []) or '—'}, wave "
             f"{m.get('wave') or '—'}. Built against baselines {', '.join(m.get('baseline_ids') or []) or '—'}.", "",
             f"Build **{record['build'].get('status')}** after {record['build'].get('rounds')} round(s)."]
    if record.get("tests"):
        lines.append(f"Tests: {record['tests'].get('status')}. Lint: {(record.get('lint') or {}).get('status', 'not run')}.")
    if record.get("recipes"):
        lines += ["", "### Recipes"] + [f"- {r['tool']} {r['version']} {r.get('args', '')}".rstrip()
                                         for r in record["recipes"]]
    if record.get("traps_handled"):
        lines += ["", "### Traps handled"] + [f"- {t}: {w}" for t, w in sorted(record["traps_handled"].items())]
    if record.get("llm_rewritten"):
        lines += ["", "### Rewritten by hand"] + [f"- `{r['file']}`: {r['reason']}" for r in record["llm_rewritten"]]
    lines += ["", "### Legacy → target", "", "| Legacy | | Target |", "|---|---|---|"]
    for e in record.get("file_map") or []:
        lines.append(f"| `{e['legacy_path']}` | {e['disposition']} | "
                     f"{('`' + e['target_path'] + '`') if e.get('target_path') else (e.get('reason') or '')} |")
    if record.get("vault_references"):
        lines += ["", "### Secrets to provision"] + [f"- {v}" for v in record["vault_references"]]
    if record.get("manual_follow_ups"):
        lines += ["", "### Left for a person"] + [f"- {f}" for f in record["manual_follow_ups"]]
    if record.get("commits"):
        lines += ["", "### Commits (by concern)"] + [f"- `{c['sha'][:10]}` {c['subject']}" for c in record["commits"]]
    preview = record.get("preview")
    if preview:
        lines += ["", f"Equivalence preview (a hint, not the verdict): {preview.get('headline')}"]
    lines += ["", "Opened by the SDLC Platform's Migration Development agent. Migration Review and Security review "
                  "it; Equivalence Testing proves it."]
    return "\n".join(lines)


def headline(record: dict) -> str:
    if record["outcome"] == "blocked":
        return f"{record['module_id']} blocked: a person must redesign it"
    parts = [f"{len(record.get('file_map') or [])} legacy file(s) mapped"]
    if record.get("recipes"):
        parts.append(f"{len(record['recipes'])} recipe(s)")
    if record.get("llm_rewritten"):
        parts.append(f"{len(record['llm_rewritten'])} rewritten by hand")
    parts.append(f"build {record['build'].get('status')}")
    if record.get("preview"):
        parts.append(record["preview"].get("headline") or "")
    return ", ".join(p for p in parts if p)


def traps_for(design: dict, module_id: str) -> list[str]:
    return sorted(t["id"] for t in (design or {}).get("traps") or [] if module_id in (t.get("affects") or []))


def scan(texts: dict[str, str]) -> dict[str, list[str]]:
    return {path: kinds for path, text in texts.items() if (kinds := rules.secrets_in(text))}

