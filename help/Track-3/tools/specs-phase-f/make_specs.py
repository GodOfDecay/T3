"""Writes the Phase F mutation specs (R46): the Migration Strategy agent, the universal pass and the
review fix wave.

    python help/Track-3/tools/specs-phase-f/make_specs.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
ST = "tests/strategy"
DM = "tests/design_modernization"
DB = {"env_test": True}

SPECS = {
    # ── Strategy: deterministic tools ────────────────────────────────────────
    "spec_f_ordering.json": {
        "target": "agents_orchestrator/strategy_agent/analysis/ordering.py",
        "tests": [f"{ST}/test_analysis.py", f"{ST}/test_checks.py"],
        "mutants": [
            ["keep-moves", '    return {m for m, ps in patterns.items() if any(p != "keep" for p in ps or [])}',
             '    return set(patterns)'],
            ["cycle-split", "                if child in on_stack:\n                    low[node] = min(low[node], index[child])",
             "                if False:\n                    low[node] = min(low[node], index[child])"],
            ["no-layering", '            level[i] = 1 + max((depth(j) for j in comp_deps[i]), default=-1)', '            level[i] = 0'],
            ["highest-risk-first", '        level[i], max(int(info[m].get("score") or 0) for m in comps[i]), _id_key(comps[i][0])))',
             '        level[i], -max(int(info[m].get("score") or 0) for m in comps[i]), _id_key(comps[i][0])))'],
            ["later-dependency-ok", "        if later:\n            out.append", "        if False:\n            out.append"],
            ["ids-not-dates", "        later = ends[b] > ends[a] if a in ends and b in ends else wave_number(b) > wave_number(a)",
             "        later = wave_number(b) > wave_number(a)"],
            ["wave-string-order", '    return int(wave_id[1:]) if re.fullmatch(r"W\\d+", wave_id or "") else 10**6',
             '    return wave_id'],
        ],
    },
    "spec_f_calendar.json": {
        "target": "agents_orchestrator/strategy_agent/analysis/calendar.py",
        "tests": [f"{ST}/test_analysis.py", f"{ST}/test_checks.py"],
        "mutants": [
            ["deadline-ignored", "        if deadline and ends > deadline:", "        if False:"],
            ["milestone-ignored", "            if when and ends > when and when != deadline:", "            if False:"],
            ["freeze-ignored", "        if freeze and due > freeze:", "        if False:"],
            ["late-baseline-ignored", "        if needed and due > needed:", "        if False:"],
            ["all-ec-ignored", '        needed = first_move if module == "all" else wave_start.get(module)',
             '        needed = wave_start.get(module)'],
            ["day-ignored", "        if allowed_days and cut_days and not (cut_days <= allowed and cut_days & allowed_days):",
             "        if False:"],
            ["night-spill-refused", "            allowed |= {(d + 1) % 7 for d in allowed_days}", "            pass"],
            ["spill-only-day-ok", "not (cut_days <= allowed and cut_days & allowed_days):", "not cut_days <= allowed:"],
            ["length-ignored", "        if limit is not None and length is not None and length > limit:", "        if False:"],
            ["window-span-not-limit", "    return limit if limit is not None else span_minutes(window)", "    return limit"],
            ["span-days-ignored", "    days = (_day(m.group(4)) - _day(m.group(1))) % 7", "    days = 0"],
            ["cut-span-unread", "        length = span_minutes(cut)", "        length = range_minutes(cut)"],
            ["timed-day-range-unread", "(?:\\s+\\d{{1,2}}(?::\\d{{2}})?\\s*(?:am|pm)?)?{_TO}", "{_TO}"],
            ["unread-part-hidden", "    elif unread:\n", "    elif False:\n"],
            ["midnight-wrong", "    return (end - start) % (24 * 60) or 24 * 60", "    return end - start"],
            ["hours-as-minutes", '    return int(round(value * 60)) if unit.startswith("h") else int(round(value))',
             '    return int(round(value))'],
            ["range-ignored", "        days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])",
             "        days.update({a, b})"],
            ["weekend-ignored", '    if re.search(r"(?i)\\bweek-?ends?\\b", text):\n        days.update({5, 6})',
             '    if False:\n        days.update({5, 6})'],
        ],
    },
    "spec_f_effort.json": {
        "target": "agents_orchestrator/strategy_agent/analysis/effort.py",
        "tests": [f"{ST}/test_analysis.py"],
        "mutants": [
            ["unmeasured-is-zero", "    if loc is None:\n        return None", "    if loc is None:\n        return 0.0"],
            ["no-coexistence-cost", '    added = sum(ADDED[p] for p in patterns if p in ADDED)', '    added = 0'],
            ["wave-with-unknown-estimated", '        if any(r is None or r["days"] is None for r in rows):', '        if False:'],
            ["kept-costed", '    if set(patterns or []) <= {"keep"}:\n        return 0.0', '    if False:\n        return 0.0'],
        ],
    },
    "spec_f_checks.json": {
        "target": "agents_orchestrator/strategy_agent/analysis/checks.py",
        "tests": [f"{ST}/test_checks.py"],
        "mutants": [
            ["unplaced-ok", "    for m in sorted(moved - set(placed)):", "    for m in []:"],
            ["foreign-module-ok", "        if m not in patterns:\n            problems.append(", "        if False:\n            problems.append("],
            ["kept-in-wave-ok", "        if m not in moved:\n            problems.append(", "        if False:\n            problems.append("],
            ["missing-patterns-ok", "        if given is None:\n            problems.append(", "        if False:\n            problems.append("],
            ["changed-pattern-ok", "        elif sorted(given) != sorted(patterns[m]):", "        elif False:"],
            ["violation-ok", "        if x is None:\n            problems.append(f\"{dependent} moves in", "        if False:\n            problems.append(f\"{dependent} moves in"],
            ["foreign-adr-ok", '        if x["adr_id"] not in design_adrs:', "        if False:"],
            ["unknown-protect-ok", "        if unknown:\n            problems.append(f\"{c['id']} protects", "        if False:\n            problems.append(f\"{c['id']} protects"],
            ["contract-uncovered-ok", "    for cid in sorted(contracts - protected):", "    for cid in []:"],
            ["trap-uncovered-ok", "    for tid in sorted(traps - protected):", "    for tid in []:"],
            ["measure-uncovered-ok", "        if key not in covered:", "        if False:"],
            ["cost-measure-required", '    measured = {words(m["metric"]): m for m in brief_measures if m.get("kind") in PROVEN_KINDS}',
             '    measured = {words(m["metric"]): m for m in brief_measures}'],
            ["invented-measure-ok", "            if words(x) not in known:", "            if False:"],
            ["exits-ok", "        if missing:\n            problems.append(f\"{w['id']}'s exit", "        if False:\n            problems.append(f\"{w['id']}'s exit"],
            ["baseline-ok", "            for c in criteria if c.get(\"protects\") and c[\"id\"] not in planned]", "            for c in criteria if False]"],
            ["parallel-ok", '        if runs and not (pr.get("required") and (pr.get("period") or "").strip()):', "        if False:"],
            ["freeze-moved-ok", "    if freeze and str(given) != str(freeze):", "    if False:"],
            ["given-dates-trusted", '        if w.get("date_status") == "given" and not {str(w.get("starts")), str(w.get("ends"))} & brief_dates:',
             "        if False:"],
            ["unreported-ok", '        if c["ref"] not in reported:', "        if False:"],
            ["effort-ok", "                for w in plan.get(\"waves\") or [] if w[\"id\"] not in have]", "                for w in []]"],
            ["budget-ok", '    if brief.get("budget") and not (plan.get("budget_fit") or "").strip():', "    if False:"],
        ],
    },
    "spec_f_packet.json": {
        "target": "agents_orchestrator/modernization_common/handover/packets.py",
        "tests": [f"{ST}/test_checks.py", "tests/modernization_common/test_handover_packets.py"],
        "mutants": [
            ["undefined-ec-ok", "        if cited:\n            raise ValueError(f\"wave criteria cite", "        if False:\n            raise ValueError(f\"wave criteria cite"],
            ["unplaced-exception-ok", "        if unplaced:\n            raise ValueError(f\"order exceptions", "        if False:\n            raise ValueError(f\"order exceptions"],
            ["w0-modules-ok", '        if self.id == "W0" and self.modules:', "        if False:"],
            ["no-entry-ok", "        if self.modules and not [c for c in self.entry_criteria if c.strip()]:", "        if False:"],
            ["duplicate-ref-ok", '        _require_unique([c.ref for c in self.calendar_conflicts if c.ref], "calendar conflict refs")', "        pass"],
        ],
    },
    # ── Strategy: tools, ledger, route (database) ────────────────────────────
    "spec_f_tool.json": {
        "target": "agents_orchestrator/strategy_agent/tools/strategy_tools.py",
        "tests": [f"{ST}/test_record_board_approval.py"], **DB,
        "mutants": [
            ["records-without-inputs", "    if missing:\n        return (\"NOT RECORDED — a migration plan", "    if False:\n        return (\"NOT RECORDED — a migration plan"],
            ["records-despite-problems", "    if problems:\n        return _refusal(problems)", "    if False:\n        return _refusal(problems)"],
            ["no-freeze", "    version = await freeze_version(STAGE, artifact)", "    version = None"],
            ["no-placements", "        placements=placements(data),", "        placements=[],"],
            ["placements-without-patterns", '"patterns": list((w.get("patterns") or {}).get(m) or []),', ""],
            ["board-no-role-check", '            if not roles & {"architect", "project_admin"}:', "            if False:"],
            ["board-no-consent", "        if not ok:\n            return None, why\n    return conn, None", "        if False:\n            return None, why\n    return conn, None"],
            ["board-read-only-ok", "        if not permits(level, mode):", "        if False:"],
            ["rejected-written", '    if status in ("rejected", "superseded"):', "    if False:"],
            ["orchestrator-memory-only", "        plan = plan or _LAST_PLAN.get(_session_key())", "        plan = _LAST_PLAN.get(_session_key())"],
            ["orchestrator-version-ignored", "        if version:\n            return None, (f\"Plan versions", "        if False:\n            return None, (f\"Plan versions"],
            ["draft-crashes", "    except (KeyError, TypeError, AttributeError) as exc:  # an incomplete draft",
             "    except ZeroDivisionError as exc:  # an incomplete draft"],
        ],
    },
    "spec_f_ledger.json": {
        "target": "shared/services/modernization_ledger.py",
        "tests": [f"{ST}/test_record_board_approval.py"], **DB,
        "mutants": [
            ["unknown-module-ok", '        if row is None:\n            raise LedgerRefused(f"{p[\'module_id\']} is not on the ledger',
             '        if row is None:\n            continue\n            raise LedgerRefused(f"{p[\'module_id\']} is not on the ledger'],
            ["rewave-migrating-ok", '        if row.state not in ("designed", "sequenced") and row.wave != p["wave"]:', "        if False:"],
            ["other-design-ok", '        if sorted(row.patterns or []) != sorted(p.get("patterns") or []):', "        if False:"],
            ["unplaced-ok", "        if row.module_id not in placed and row.state in", "        if False and row.state in"],
            ["criteria-rewritten", '        if row.state not in ("designed", "sequenced") and sorted(row.ec_ids or [])',
             "        if False and sorted(row.ec_ids or [])"],
            ["revision-not-recorded", '                                             artifact=artifact, note="plan revised")]',
             '                                             artifact=artifact)]'],
        ],
    },
    "spec_f_route.json": {
        "target": "shared/routers/artifact_versions.py",
        "tests": [f"{ST}/test_record_board_approval.py"], **DB,
        "mutants": [
            ["approval-skips-ledger", '    elif stage == "strategy":\n        await _strategy_approved', '    elif False:\n        await _strategy_approved'],
            ["no-placements-approved", "    if not placements:\n        raise HTTPException(status_code=409", "    if False:\n        raise HTTPException(status_code=409"],
            ["refusal-swallowed", "    except ledger.LedgerRefused as exc:\n        raise HTTPException(status_code=409, detail=f\"Not approved: {exc}\") from exc\n\n\nasync def _design_approved",
             "    except ledger.LedgerRefused as exc:\n        pass\n\n\nasync def _design_approved"],
        ],
    },
    "spec_f_router.json": {
        "target": "shared/routers/modernization.py",
        "tests": [f"{ST}/test_record_board_approval.py"], **DB,
        "mutants": [
            ["strategy-packet-is-design", '"design_modernization": design_packet, "strategy": plan_packet}[stage]',
             '"design_modernization": design_packet, "strategy": design_packet}[stage]'],
            ["artifact-routes-legacy-only", "    if stage not in (set(_KINDS.values()) if artifact else TRACK3_STAGES):",
             "    if stage not in TRACK3_STAGES:"],
        ],
    },
    # The Phase E Orchestrator guard moved here (the shared reader); its old spec_e_tool anchor is gone.
    "spec_f_inputs.json": {
        "target": "agents_orchestrator/modernization_common/inputs.py",
        "tests": [f"{ST}/test_record_board_approval.py", f"{DM}/test_record_tool.py", f"{ST}/test_agent.py"], **DB,
        "mutants": [
            ["orchestrator-reads-pages", "            if get_orchestrator_run():\n                run_id", "            if False:\n                run_id"],
            ["pins-ignored", "            for pin in turn_built_from() or []:", "            for pin in []:"],
            ["db-error-is-nothing", "        for item in out.values():\n            item.problems = [\"It could not",
             "        for item in []:\n            item.problems = [\"It could not"],
        ],
    },
    # ── the universal pass ───────────────────────────────────────────────────
    "spec_f_brief_emit.json": {
        "target": "agents_orchestrator/modernization_common/handover/emit.py",
        "tests": [f"{DM}/test_universal.py"],
        "mutants": [
            ["freeze-not-handed", '    freeze = next((m["date"] for m in milestones if m["kind"] == "freeze"), None)', "    freeze = None"],
            ["prose-deadline-lost", '    due = _iso_date(deadline) or next((m["date"] for m in milestones if m["kind"] == "deadline"), None)',
             "    due = _iso_date(deadline)"],
            ["undated-milestone-guessed", "        if when and (m.get(\"label\") or \"\").strip():", "        if (m.get(\"label\") or \"\").strip():"],
            ["window-dropped", '        "downtime_window": (brief.get("downtime_window") or "").strip() or None,', '        "downtime_window": None,'],
        ],
    },
    "spec_f_eol.json": {
        "target": "agents_orchestrator/discovery_agent/analysis/eol.py",
        "tests": [f"{DM}/test_universal.py"],
        "mutants": [
            ["mysql-patch-unread", '    if name in {"Python", "MySQL", "PHP", "Ruby", "Go"}:', '    if name in {"Python"}:'],
            ["pg-major-unread", '        return parts[0] if parts[0].isdigit() and int(parts[0]) >= 10 else ".".join(parts[:2])',
             '        return ".".join(parts[:2])'],
            ["go-minimum-scored", "    if runtime.minimum and runtime.name in _MINIMUM_NOT_SCORED:", "    if False:"],
            ["every-minimum-unscored", '_MINIMUM_NOT_SCORED = {"Go"}', '_MINIMUM_NOT_SCORED = {"Go", "Node.js", "Python"}'],
            ["minimum-not-labelled", '    if runtime.minimum and status.status != "unknown":', "    if False:"],
            ["mysql80-supported", '"8.0": _Lifecycle(date(2026, 4, 30)), "8.4": _Lifecycle(date(2032, 4, 30)),',
             '"8.0": _Lifecycle(date(2032, 4, 30)), "8.4": _Lifecycle(date(2032, 4, 30)),'],
        ],
    },
    "spec_f_manifests.json": {
        "target": "agents_orchestrator/discovery_agent/analysis/manifests.py",
        "tests": [f"{DM}/test_universal.py"],
        "mutants": [
            ["toolchain-unread", "            if toolchain:\n", "            if False:\n"],
            ["go-line-is-runtime", 'Runtime("Go", m.group(1), minimum=True)', 'Runtime("Go", m.group(1))'],
            ["node-range-is-runtime", '    minimum = bool(re.match(r"\\s*>", engine) or "||" in engine or re.search(r"\\d\\s+-\\s+\\d", engine))',
             "    minimum = False"],
            ["node-or-range-is-runtime", ' or "||" in engine or re.search', " or re.search"],
            ["nvmrc-loses-to-minimum", "    if (not engine or minimum) and nvmrc.exists()", "    if not engine and nvmrc.exists()"],
            ["python-range-is-runtime", 'minimum=bool(re.match(r"\\s*(?:>|~=|\\^)", value))', "minimum=False"],
            ["python-caret-is-runtime", 'minimum=bool(re.match(r"\\s*(?:>|~=|\\^)", value))', 'minimum=bool(re.match(r"\\s*(?:>|~=)", value))'],
            ["pin-file-loses-to-minimum", "        if (facts.runtime is None or facts.runtime.minimum) and path.exists():",
             "        if facts.runtime is None and path.exists():"],
        ],
    },
    "spec_f_design_checks.json": {
        "target": "agents_orchestrator/design_modernization_agent/analysis/checks.py",
        "tests": [f"{DM}/test_universal.py", f"{DM}/test_checks.py"],
        "mutants": [
            ["managed-mysql-unread", '    ("MySQL", re.compile(r"(?i)\\bmysql(?:\\s+[a-z][\\w-]*){0,3}?\\s*v?(\\d+\\.\\d+)")),',
             '    ("MySQL", re.compile(r"(?i)\\bmysql\\s*v?(\\d+\\.\\d+)")),'],
            ["sqlserver-unread", '    ("SQL Server", re.compile(r"(?i)\\bsql\\s*server(?:\\s+[a-z][\\w-]*){0,3}?\\s*(\\d{4})\\b")),', ""],
            ["replaced-read", "            if _REPLACED.search(text[max(0, m.start() - 60):m.start()]):", "            if False:"],
            ["replaced-past-to", "(?:(?!(?:to|onto|into|with)\\b)[\\w-]+\\s+){0,4}$", "(?:[\\w-]+\\s+){0,4}$"],
        ],
    },
    "spec_f_scanner.json": {
        "target": "agents_orchestrator/design_modernization_agent/analysis/interfaces.py",
        "tests": [f"{DM}/test_universal.py", f"{DM}/test_interfaces.py"],
        "mutants": [
            ["go-router-unread", "        elif lang == \"go\":\n            _go(lines, emit)", "        elif lang == \"go\":\n            pass"],
            ["vb-unread", "        elif lang == \"vb\":\n            _vb(lines, emit)", "        elif lang == \"vb\":\n            pass"],
            ["cobol-sql-unread", "        elif lang == \"cobol\":\n            _cobol_sql(lines, emit)", "        elif lang == \"cobol\":\n            pass"],
            # "jcl-comment-read" (return False) is EQUIVALENT: both JCL rules need `//name<space>`, which `//*`
            # never matches — recorded in build-log Entry 12, not run.
            ["jcl-statements-skipped", '        return s.startswith("//*")  # every JCL statement starts with //; only //* is a comment', '        return s.startswith("//")'],
            ["cobol-comment-read", '        return (len(line) > 6 and line[6] in "*/") or s.startswith(("*>", "*"))', "        return False"],
            ["php-attribute-skipped", '        if s.startswith("#[") or (s.startswith("*") and "@Route" in s):', "        if False:"],
            ["php-docblock-skipped", '(s.startswith("*") and "@Route" in s)', "False"],
            ["declared-unread", "        if declared:\n            _declared(ext, text, lines, emit)", "        if False:\n            _declared(ext, text, lines, emit)"],
            ["openapi-past-paths", "                elif line and not line[0].isspace() and not stripped.startswith((\"}\", \"]\", \"#\")):\n                    in_paths = False",
             "                elif False:\n                    in_paths = False"],
            ["graphql-any-type", '            if line.strip().startswith("}"):\n                root = ""', '            if False:\n                root = ""'],
            ["proto-no-service", "                emit(\"rpc\", \"exposes\", f\"gRPC {service + '.' if service else ''}{r.group(1)}\", n, line)",
             "                emit(\"rpc\", \"exposes\", f\"gRPC {r.group(1)}\", n, line)"],
            ["cronjob-any-yaml", '    if ext in (".yaml", ".yml") and _K8S_CRONJOB.search(text):', '    if ext in (".yaml", ".yml"):'],
        ],
    },
    "spec_f_broker.json": {
        "target": "config/context_broker.py",
        "tests": [f"{ST}/test_agent.py"],
        "mutants": [
            ["cut-silently", "    if len(modules) > 60:", "    if False:"],
        ],
    },
    # ── frontend ─────────────────────────────────────────────────────────────
    "spec_f_ui.json": {
        "root": "frontend", "target": "components/modernization/strategy-view.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/strategy-page.test.tsx"],
        "mutants": [
            ["ledger-claims-rejected", '  if (status === "rejected") return', "  if (false) return"],
            ["ledger-no-refetch", "    if (approved) void refetch();", "    if (false) void refetch();"],
            ["other-wave-hidden", '                  {stateLabel(row.state)}{row.wave && row.wave !== p.wave ? ` in ${row.wave}` : ""}',
             "                  {stateLabel(row.state)}"],
            ["late-baseline-unflagged", "                {late.has(b.ec_id) && <Badge", "                {false && <Badge"],
            ["open-shown-resolved", '                  {r?.resolution ? "resolved" : reported.has(c.ref) ? "reported — open" : "not reported"}',
             '                  {"resolved"}'],
            ["user-raised-hidden", "        {userRaised.map((c) => (", "        {[].map((c: never) => ("],
            ["freeze-not-marked", '  if (freeze) out.push({ key: "freeze"', "  if (false) out.push({ key: \"freeze\""],
            ["cycle-unmarked", "                  {s.cycle && <Badge", "                  {false && <Badge"],
            ["criteria-unfiltered", '  const shown = module === "all-modules" ? plan.equivalence_criteria : plan.equivalence_criteria.filter((c) => c.module_id === module);',
             "  const shown = plan.equivalence_criteria;"],
            ["exceptions-hidden", "      {plan.order_exceptions.length > 0 && (", "      {false && ("],
        ],
    },
    "spec_f_ui_frame.json": {
        "root": "frontend", "target": "components/modernization/track3-agent-page.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/strategy-page.test.tsx",
                "__tests__/app/target-architecture-page.test.tsx", "__tests__/app/track3-pages-retrofit.test.tsx"],
        "mutants": [
            ["legacy-queried-anyway", "  const legacyQ = useLegacyCode(projectId, phase, showLegacyCode);", "  const legacyQ = useLegacyCode(projectId, phase, true);"],
            ["pull-shown-anyway", "            {showLegacyCode && (\n              <Button", "            {true && (\n              <Button"],
        ],
    },
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(name, len(spec["mutants"]))
