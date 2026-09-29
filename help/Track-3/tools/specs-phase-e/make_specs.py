"""Writes the Phase E mutation specs (R46). Kept beside them so a spec can be re-derived.

    python help/Track-3/tools/specs-phase-e/make_specs.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
DM = "tests/design_modernization"

SPECS = {
    "spec_e_checks.json": {
        "target": "agents_orchestrator/design_modernization_agent/analysis/checks.py",
        "tests": [f"{DM}/test_checks.py", f"{DM}/test_review_fixes.py"],
        "mutants": [
            ["unknown-id-accepted", "        if known is None:\n", "        if known is None and False:\n"],
            ["name-drift-accepted", 'if words(m["module"]) != words(known["name"]):', "if False:"],
            ["score-change-accepted", 'if m["tier"] != known["tier"] or int(m["risk_score"]) != int(known["score"]):',
             'if m["tier"] != known["tier"]:'],
            ["missing-module-accepted", "        if mid not in designed:", "        if False:"],
            ["mnc-unfrozen-accepted", "        if key not in claimed:", "        if False:"],
            ["mnc-foreign-accepted", "        if key not in wanted:", "        if False:"],
            ["mnc-exact-compare", '    return text.strip("\\"\'“”‘’ .").casefold()', "    return text"],
            ["location-unchecked", "        if not hit:\n", "        if False:\n"],
            ["confirmed-unchecked",
             '        if not words(c.get("brief_item") or "") and not _shown_by_inventory(',
             '        if False and not _shown_by_inventory('],
            # fix wave (review #1-#4)
            ["confirmed-multi-file", "        if len(hit) != 1:", "        if False:"],
            ["confirmed-any-line", "    return line is None or not lines or any(abs(line - n) <= LINE_SLACK for n in lines)",
             "    return True"],
            ["unknown-version-silent", '            elif status.status == "unknown":', "            elif False:"],
            ["engine-ignored", '        is_db = _DATABASE_LAYER.search(layer["layer"]) or _DATABASE_ENGINE.search(f"{layer[\'today\']} {layer[\'target\']}")',
             '        is_db = _DATABASE_LAYER.search(layer["layer"])'],
            ["no-code-confirmed-accepted",
             '            if c["status"] == "confirmed" and not words(c.get("brief_item") or ""):\n                out.problems',
             "            if False:\n                out.problems"],
            ["trap-no-path-accepted", "        if not paths:", "        if False:"],
            ["trap-unresolved-accepted", "        elif not any(resolve(p, files, dirs) for p in paths):", "        elif False:"],
            ["elision-unresolved", '    if "..." in loc:', "    if False:"],
            ["glob-unresolved", '    if any(ch in loc for ch in "*?["):', "    if False:"],
            ["folder-unresolved", '    if loc.rstrip("/") in dirs:', "    if False:"],
            ["eol-accepted", '            if status.status == "eol":', "            if False:"],
            ["approaching-accepted", '            elif status.status == "approaching":', "            elif False:"],
            ["latest-accepted", '        if _LATEST.search(text or ""):', "        if False:"],
            # "framework-read-as-net" SURVIVED in the first run: the skip it removed was redundant
            # (the ".NET" pattern needs digits right after ".NET"), so the code was deleted.
            ["framework-matched-as-net", '    (".NET", re.compile(r"(?i)\\.net\\s*v?(\\d+(?:\\.\\d+)?)")),',
             '    (".NET", re.compile(r"(?i)\\.net\\s*\\w*\\s*v?(\\d+(?:\\.\\d+)?)")),'],
            ["data-migration-optional", '        if is_db and words(layer["today"]) != words(layer["target"]):', '        if False:'],
            ["unchanged-db-needs-plan", '        if is_db and words(layer["today"]) != words(layer["target"]):', '        if is_db:'],
            ["diagram-missing-accepted", '        if not any(pattern.search(d["title"]) for d in diagrams):', "        if False:"],
            ["non-mermaid-accepted", '        if not _MERMAID_START.match(_first_statement(d["mermaid"])):', "        if False:"],
            ["front-matter-unread", '    if lines and lines[0].strip() == "---":', "    if False:"],
            ["question-unasked-accepted", "        if key in answered or any(key in o for o in still_open):", "        if True:"],
            ["open-question-refused", "        if key in answered or any(key in o for o in still_open):", "        if key in answered:"],
            ["one-letter-mutes", "        if key in answered or any(key in o for o in still_open):",
             "        if key in answered or any(key in o or o in key for o in still_open if o):"],
        ],
    },
    "spec_e_tool.json": {
        "target": "agents_orchestrator/design_modernization_agent/tools/design_tools.py",
        "tests": [f"{DM}/test_record_tool.py"],
        "mutants": [
            ["records-without-inputs", "    if missing:\n        return \"NOT RECORDED", "    if False:\n        return \"NOT RECORDED"],
            ["records-despite-problems", "    if problems:\n        return _refusal(problems)", "    if False:\n        return _refusal(problems)"],
            ["no-freeze", "    version = await freeze_version(STAGE, artifact)", "    version = None"],
            ["no-persist", "    saved = await _persist(artifact)", "    saved = \"Saved to the project as the current target design.\""],
            ["orchestrator-reads-pages", "            if get_orchestrator_run():\n                run_id", "            if False:\n                run_id"],
            ["draft-not-said", '        if item.version is not None and item.status == "draft":', "        if False:"],
            ["commit-drift-not-said", "    if assessed and pulled and not (assessed.startswith(pulled[:7]) or pulled.startswith(assessed[:7])):",
             "    if False:"],
            ["checked-without-code", "    if root is not None:\n        files, dirs", "    if False:\n        files, dirs"],
        ],
        "env_test": True,
    },
    "spec_e_ledger.json": {
        "target": "shared/services/modernization_ledger.py",
        "tests": [f"{DM}/test_approval_and_routes.py"],
        "env_test": True,
        "mutants": [
            ["drift-accepted",
             '        if existing is not None and path and (existing.legacy_path or "").strip().strip("/") not in ("", path):',
             "        if False:"],
            ["drift-trailing-slash", '        path = (m.get("legacy_path") or "").strip().strip("/")',
             '        path = (m.get("legacy_path") or "").strip()'],
        ],
    },
    "spec_e_route.json": {
        "target": "shared/routers/artifact_versions.py",
        "tests": [f"{DM}/test_approval_and_routes.py"],
        "env_test": True,
        "mutants": [
            ["approval-skips-ledger", '    if stage == "design_modernization":\n        await _design_approved',
             '    if False:\n        await _design_approved'],
            ["refusal-swallowed", '        raise HTTPException(status_code=409, detail=f"Not approved: {exc}") from exc', "        pass"],
            ["path-not-passed", '"legacy_path": paths.get(m.get("module_id")) or "",', '"legacy_path": "",'],
        ],
    },
    "spec_e_router.json": {
        "target": "shared/routers/modernization.py",
        "tests": [f"{DM}/test_approval_and_routes.py"],
        "env_test": True,
        "mutants": [
            ["packet-uses-assessment", '             "design_modernization": design_packet}[stage]', '             "design_modernization": assessment_packet}[stage]'],
            ["interfaces-unguarded", '    resolved, _tenant, _user = await _guard(db, request, project_id, stage)\n    pull = legacy_code.current_pull(resolved)',
             '    resolved = project_id\n    pull = legacy_code.current_pull(resolved)'],
            ["interfaces-ids-dropped", "               for m in ((row.payload or {}).get(\"modules\") if row is not None else None) or [] if m.get(\"id\")]",
             "               for m in [] if m.get(\"id\")]"],
        ],
    },
    "spec_e_emit.json": {
        "target": "agents_orchestrator/modernization_common/handover/emit.py",
        "tests": [f"{DM}/test_approval_and_routes.py"],
        "env_test": True,
        "mutants": [
            ["page-fields-handed-over", "    return {name: design[name] for name in DesignPayload.model_fields if name in design}",
             "    return dict(design)"],
        ],
    },
    "spec_e_interfaces.json": {
        "target": "agents_orchestrator/design_modernization_agent/analysis/interfaces.py",
        "tests": [f"{DM}/test_interfaces.py"],
        "mutants": [
            ["class-prefix-lost", "                prefix = m.group(1)\n                continue", "                prefix = \"\"\n                continue"],
            ["jaxrs-method-path-lost", "                    path = p.group(1)\n                    break", "                    break"],
            ["vendored-read", "            if is_vendored_asset(\"\" if rel_dir == \".\" else rel_dir, name):\n                continue",
             "            if False:\n                continue"],
            ["sibling-folder-matches", "        elif rel == path or rel.startswith(path + \"/\"):", "        elif rel.startswith(path):"],
            ["cap-silent", "    truncated = len(items) > MAX_ITEMS", "    truncated = False"],
            ["literal-not-extracted", "    if quoted:\n        return quoted.group(1).strip()[:160]", "    if False:\n        return quoted.group(1).strip()[:160]"],
            ["request-method-ignored", "                verb = rm.group(1).upper() if rm else \"ANY\"", "                verb = \"ANY\""],
            ["python-write-read-swapped", "            emit(\"file\", \"writes\" if any(c in mode for c in \"wax\") else \"reads\", _clean(m.group(1)), n, line)",
             "            emit(\"file\", \"reads\", _clean(m.group(1)), n, line)"],
        ],
    },
    "spec_e_ui_view.json": {
        "root": "frontend",
        "target": "components/modernization/target-design-view.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/target-architecture-page.test.tsx"],
        "mutants": [
            ["ledger-no-refetch", "    if (approved) void refetch();", "    if (false) void refetch();"],
            ["ledger-claims-before-approval", "        {approved\n", "        {true\n"],
            ["proposed-shown-confirmed", '              {c.status === "confirmed" ? "Confirmed" : "Proposed — needs confirming"}', '              {"Confirmed"}'],
            ["brief-words-hidden", "          {c.brief_item && (", "          {false && ("],
            ["chosen-exact-only", "  return adr.options.find((o) => norm(o) === d) ?? adr.options.find((o) => d.startsWith(norm(o))) ?? null;",
             "  return adr.options.find((o) => norm(o) === d) ?? null;"],
            ["unchecked-code-not-said", "      {design.interfaces ? (", "      {true ? ("],
            ["notes-hidden", "        {design.notes.length > 0 && (", "        {false && ("],
            ["module-traps-unjoined", "  const traps = design.traps.filter((t) => t.affects.includes(module.module_id));", "  const traps: DesignTrap[] = [];"],
        ],
    },
    "spec_e_ui_handover.json": {
        "root": "frontend",
        "target": "components/modernization/version-view.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/target-architecture-page.test.tsx",
                "__tests__/app/track3-pages-retrofit.test.tsx"],
        "mutants": [
            ["design-hands-to-itself", '  design_modernization: "Migration Strategy",', '  design_modernization: "Target Architecture",'],
        ],
    },
    "spec_e_ui_dialog.json": {
        "root": "frontend",
        "target": "components/modernization/legacy-interfaces-dialog.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/target-architecture-page.test.tsx"],
        "mutants": [
            ["kind-filter-ignored", '  const rows = inv.items.filter((i) => (kind === "all" || i.kind === kind) &&', "  const rows = inv.items.filter((i) => (true) &&"],
            ["text-filter-ignored", "    (!needle || `${i.name} ${i.location} ${i.module}`.toLowerCase().includes(needle)));", "    (true));"],
        ],
    },
}

# ── the fix wave (review findings, build-log Entry 11) ──────────────────────
SPECS["spec_e_ledger.json"]["mutants"] = [
    ["drift-accepted", "        if path and by_id.get(m[\"module_id\"]) not in (None, \"\", path):", "        if False:"],
    ["drift-trailing-slash", "    by_id = {r.module_id: (r.legacy_path or \"\").strip().strip(\"/\") for r in held_rows}",
     "    by_id = {r.module_id: (r.legacy_path or \"\") for r in held_rows}"],
    ["other-direction-accepted", "        if path and held and held != m[\"module_id\"]:", "        if False:"],
]
SPECS["spec_efix_route.json"] = {
    "target": "shared/routers/artifact_versions.py", "tests": [f"{DM}/test_approval_and_routes.py"], "env_test": True,
    "mutants": [["unplaced-approved", "    if unplaced:\n        raise HTTPException(", "    if False:\n        raise HTTPException("]],
}
SPECS["spec_efix_interfaces.json"] = {
    "target": "agents_orchestrator/design_modernization_agent/analysis/interfaces.py",
    "tests": [f"{DM}/test_review_fixes.py", f"{DM}/test_interfaces.py"],
    "mutants": [
        ["symlink-followed", "            if path.is_symlink():\n                continue", "            if False:\n                continue"],
        ["cs-method-route-replaces", "            method_route = (route.group(1), n)", "            prefix = route.group(1)"],
        ["jaxrs-window-crosses-methods",
         "            for i in [*_annotation_block(lines, n - 1, -1), *_annotation_block(lines, n - 1, +1)]:",
         "            for i in range(max(0, n - 4), min(len(lines), n + 3)):"],
        ["py-mode-ignored", "            mode = next((mm.group(1) for a in args[1:] if (mm := _PY_MODE.match(a))), \"r\")",
         "            mode = \"r\""],
        ["py-split-inside-parens", "        elif ch == \",\" and depth == 0:", "        elif ch == \",\":"],
        ["prose-is-sql", "if t.group(2).lower() not in _SQL_NOT_TABLES and _SQL_SHAPE[t.group(1).lower()].search(text):",
         "if t.group(2).lower() not in _SQL_NOT_TABLES:"],
    ],
}
SPECS["spec_efix_tool.json"] = {
    "target": "agents_orchestrator/design_modernization_agent/tools/design_tools.py",
    "tests": [f"{DM}/test_record_tool.py"], "env_test": True,
    "mutants": [
        ["commit-drift-recorded", "    if commit_note:\n        problems.append(", "    if False:\n        problems.append("],
        ["cache-ignores-modules", "    key = (str(root), commit or \"\", tuple(", "    key = (str(root), commit or \"\") or tuple("],
        ["export-prefers-chat-copy", "    if get_orchestrator_run() or not (get_project_id() and get_tenant_id()):\n        return _LAST_DESIGN",
         "    if True:\n        return _LAST_DESIGN"],
    ],
}
SPECS["spec_efix_ui.json"] = {
    "root": "frontend", "target": "components/modernization/target-design-view.tsx",
    "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/target-architecture-page.test.tsx"],
    "mutants": [
        ["rejected-promises-approval", '  if (status === "rejected") return', '  if (false) return'],
        ["superseded-promises-approval", '  if (status === "superseded") {', '  if (false) {'],
    ],
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(name, len(spec["mutants"]))
