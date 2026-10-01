"""Writes the Phase G mutation specs (R46): the legacy sandbox and Equivalence Testing (Baseline mode).

    python help/Track-3/tools/specs-phase-g/make_specs.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
T = "tests/testing_modernization"
DB = {"env_test": True}

SPECS = {
    "spec_g_profile.json": {
        "target": "agents_orchestrator/testing_modernization_agent/sandbox/profile.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["outside-checkout-ok", "        path.relative_to(root)\n    except ValueError:\n        return None",
             "        pass\n    except ValueError:\n        return None"],
            ["absolute-ok", '    if not isinstance(rel, str) or not rel.strip() or rel.startswith(("/", "\\\\")) or ":" in rel:',
             '    if not isinstance(rel, str) or not rel.strip():'],
            ["unpinned-base-ok", "        if image.lower() not in stages and not DIGEST_RE.search(image):", "        if False:"],
            ["real-data-ok", '    if p.get("data") not in DATA_KINDS:', "    if False:"],
            ["version-any", '    if p.get("version") != 1:', "    if False:"],
            ["root-writable-ok", 'w.strip("/") == ""', "False"],
            ["bad-port-ok", "                or not isinstance(port, int) or not 0 < port < 65536 \\", "                or False \\"],
            ["reserved-stub-name-ok", '        if s["name"] in stub_names or s["name"] == "app":', '        if s["name"] in stub_names:'],
            ["bad-env-ok", '        if not _ENV_RE.match(str(s.get("env", ""))):', "        if False:"],
            ["duplicate-scenario-ok", '        if sc["id"] in seen:\n            problems.append(f"{where}: the id is used twice.")',
             '        if False:\n            problems.append(f"{where}: the id is used twice.")'],
            ["http-without-service-ok", "            if service is None:\n                problems.append(f\"{where} sends HTTP requests",
             "            if False:\n                problems.append(f\"{where} sends HTTP requests"],
            ["shell-in-output-ok", '        and bool(re.fullmatch(r"[A-Za-z0-9._*?-]+", name))', "        and bool(name)"],
            ["glob-dir-ok", '    return directory not in ("", "/") and "*" not in directory and "?" not in directory \\',
             '    return directory not in ("", "/") \\'],
            ["bad-method-ok", '        if not isinstance(req, dict) or str(req.get("method", "")).upper() not in _METHODS:',
             "        if not isinstance(req, dict):"],
            ["ui-kind-ok", '        else:\n            problems.append(f"{where}: kind must be http or batch',
             '        elif False:\n            problems.append(f"{where}: kind must be http or batch'],
        ],
    },
    "spec_g_images.json": {
        "target": "agents_orchestrator/testing_modernization_agent/sandbox/images.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["unpinned-harness-ok", "    if not DIGEST_RE.search(image):", "    if False:"],
        ],
    },
    "spec_g_noise.json": {
        "target": "agents_orchestrator/testing_modernization_agent/analysis/noise.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["timestamp-shown", "    if _TS.match(text):\n        return \"<timestamp>\"", "    if False:\n        return \"<timestamp>\""],
            ["uuid-shown", "    if _UUID.match(text):\n        return \"<uuid>\"", "    if False:\n        return \"<uuid>\""],
            ["letters-shown", 'shape = re.sub(r"[A-Za-z\\u00c0-\\u024f]", "A", re.sub(r"\\d", "9", text))',
             'shape = re.sub(r"\\d", "9", text)'],
            ["digits-shown", 'shape = re.sub(r"[A-Za-z\\u00c0-\\u024f]", "A", re.sub(r"\\d", "9", text))',
             'shape = re.sub(r"[A-Za-z\\u00c0-\\u024f]", "A", text)'],
            ["status-ignored", '        fx = {k: v for k, v in x.items() if k != "request" and k != "body"} | {',
             '        fx = {} | {'],
            ["missing-file-ok", '        if name not in fa or name not in fb:\n            varying[name]',
             '        if name not in fa or name not in fb:\n            continue\n            varying[name]'],
            ["extra-line-ok", "        for n in range(max(len(la), len(lb))):", "        for n in range(min(len(la), len(lb))):"],
            ["exit-ignored", '    if ea.get("exit") != eb.get("exit"):', "    if False:"],
            ["suffix-too-broad", '    return field == rule or field.endswith("." + rule) or fnmatch.fnmatchcase(field, rule)',
             '    return field == rule or field.endswith(rule) or fnmatch.fnmatchcase(field, rule)'],
            ["empty-rule-covers", "    if not rule:\n        return False", "    if not rule:\n        return True"],
        ],
    },
    "spec_g_baseline.json": {
        "target": "agents_orchestrator/testing_modernization_agent/analysis/baseline.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["foreign-ec-ok", '        if ec not in ecs:\n            problems.append(f"{ec} is not a criterion of the approved plan.")\n            continue',
             '        if False:\n            problems.append(f"{ec} is not a criterion of the approved plan.")\n            continue'],
            ["empty-mapping-ok", "        if not isinstance(scs, list) or not scs:", "        if not isinstance(scs, list):"],
            ["unknown-scenario-ok", "        if unknown:\n            problems.append(f\"{ec} is mapped to", "        if False:\n            problems.append(f\"{ec} is mapped to"],
            ["partial-module-ok", '        if (c["module_id"] in touched or c["module_id"] == "all") and ec not in mapping and ec not in skipped:',
             "        if False:"],
            ["all-optional", '        if (c["module_id"] in touched or c["module_id"] == "all") and ec not in mapping and ec not in skipped:',
             '        if c["module_id"] in touched and ec not in mapping and ec not in skipped:'],
            ["reasonless-ok", "        elif len(reason) < 3:", "        elif False:"],
            ["both-ok", "        elif ec in mapping:\n            problems.append(f\"{ec} is both mapped", "        elif False:\n            problems.append(f\"{ec} is both mapped"],
            ["invented-proposal-ok", "        if ec not in need or fld not in need[ec]:", "        if False:"],
            ["ruleless-ok", "        elif not rule:\n            problems.append(", "        elif False:\n            problems.append("],
            ["missing-proposal-ok", "            if (ec, fld) not in given:", "            if False:"],
            ["rules-ignored", '        rest = sorted(set(fields) - set(covered(fields, ecs[ec].get("normalization") or [])))',
             "        rest = sorted(set(fields))"],
            ["one-baseline-per-ec", '        groups.setdefault((ecs[ec]["module_id"], tuple(sorted(mapping[ec]))), []).append(ec)',
             '        groups.setdefault((ecs[ec]["module_id"], tuple(sorted(mapping[ec])), ec), []).append(ec)'],
            ["unit-always-cases", '            "unit": "cases" if "http" in kinds else "runs",', '            "unit": "cases",'],
            ["shared-not-shared", '    return [{"module_id": m, "baseline_ids": [b["id"] for b in payload["baselines"] if b["module_id"] == m] + shared}',
             '    return [{"module_id": m, "baseline_ids": [b["id"] for b in payload["baselines"] if b["module_id"] == m]}'],
            ["model-evidence", '"evidence": evidence(p["ec_id"], p["field"], mapping, noise)}', '"evidence": str(p.get("evidence") or "given")}'],
        ],
    },
    "spec_g_packet.json": {
        "target": "agents_orchestrator/modernization_common/handover/packets.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["both-captured-ok", "        if both:\n            raise ValueError(f\"{', '.join(both)} are both baselined",
             "        if False:\n            raise ValueError(f\"{', '.join(both)} are both baselined"],
            ["duplicate-not-captured-ok", '        _require_unique([n.ec_id for n in self.not_captured], "criteria not captured")', "        pass"],
        ],
    },
    "spec_g_store.json": {
        "target": "agents_orchestrator/testing_modernization_agent/store.py",
        "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["any-capture-id", "        if not _CAPTURE_RE.match(capture_id or \"\"):\n            raise ValueError", "        if False:\n            raise ValueError"],
            ["any-scenario-id", "            if not _SCENARIO_RE.match(sid):", "            if False:"],
            ["run2-hashed", '        run1 = self.capture_dir(project_id, capture_id) / "run1"', '        run1 = self.capture_dir(project_id, capture_id) / "run2"'],
            ["kept-purged", '            if m.get("keep") or not until or datetime.fromisoformat(until) > now:',
             '            if not until or datetime.fromisoformat(until) > now:'],
            ["fresh-purged", '            if m.get("keep") or not until or datetime.fromisoformat(until) > now:',
             '            if m.get("keep") or not until:'],
        ],
    },
    "spec_g_runner.json": {
        "target": "agents_orchestrator/testing_modernization_agent/sandbox/runner.py",
        "tests": [f"{T}/test_sandbox.py"],
        "mutants": [
            ["egress-open", '        docker("network", "create", "--internal", *self._labels(), self.net)',
             '        docker("network", "create", *self._labels(), self.net)'],
            ["no-cleanup", "    finally:\n        cleanup(capture_id)\n        docker(\"rmi\", \"-f\", tag, check=False)",
             "    finally:\n        docker(\"rmi\", \"-f\", tag, check=False)"],
            ["image-kept", "        cleanup(capture_id)\n        docker(\"rmi\", \"-f\", tag, check=False)", "        cleanup(capture_id)"],
            ["one-run", "        for n in range(1, runs + 1):", "        for n in range(1, 2):"],
            ["unhealthy-ok", "            if self._driver(\"wait\", url, str(health_seconds()), timeout=health_seconds() + 30).returncode != 0:",
             "            if False:"],
            ["no-reseed", "        script = f\"set -e\\n{seed}\\n{main}\" if seed else main", "        script = main"],
            ["files-lost", "                        (files / name).write_bytes(data)", "                        pass"],
        ],
    },
    "spec_g_tool.json": {
        "target": "agents_orchestrator/testing_modernization_agent/tools/equivalence_tools.py",
        "tests": [f"{T}/test_record_approval.py"], **DB,
        "mutants": [
            ["orchestrator-captures", "    if get_orchestrator_run():\n        return None, (\"A baseline is captured",
             "    if False:\n        return None, (\"A baseline is captured"],
            ["draft-plan-ok", "    if not _approved(plan):", "    if False:"],
            ["mapping-unchecked", "    if found:\n        return None, _problems_text(\"The capture plan does not hold:\"",
             "    if False:\n        return None, _problems_text(\"The capture plan does not hold:\""],
            ["unsequenced-ok", '             if m not in rows or rows[m]["state"] not in ("sequenced", "baselined")]', "             if False]"],
            ["any-role-captures", "    return bool(roles & CAPTURE_ROLES)", "    return True"],
            ["no-consent", "    ok, why = await _may_capture()\n    if not ok:\n        return why", "    ok, why = await _may_capture()"],
            ["partial-kept", '    out = store.capture_dir(project_id, manifest["id"])\n    for sub in ("run1", "run2"):',
             '    out = store.capture_dir(project_id, manifest["id"])\n    for sub in ():'],
            # ── fix wave: the shared lock, a stopped capture, tidying, who saves the profile, audit ──
            ["lock-ignored", '    if not store.acquire_lock(project_id, capture_id):\n        return "A capture is already running',
             '    if False:\n        return "A capture is already running'],
            ["lock-never-released", "        if not released:\n            store.release_lock(project_id, capture_id)",
             "        if False:\n            store.release_lock(project_id, capture_id)"],
            ["cancel-releases-early", "            released = True\n", "            released = False\n"],
            ["cancel-not-marked", '            _fail(store, project_id, manifest, "cancelled: the capture was stopped before it finished.")',
             "            pass"],
            ["cancel-lock-kept", "        pass\n    out = store.capture_dir(project_id, capture_id)\n    for sub in (\"run1\", \"run2\"):\n        shutil.rmtree(out / sub, ignore_errors=True)\n    store.release_lock(project_id, capture_id)",
             "        pass\n    out = store.capture_dir(project_id, capture_id)\n    for sub in (\"run1\", \"run2\"):\n        shutil.rmtree(out / sub, ignore_errors=True)"],
            ["no-reap", "    for gone in store.reap_interrupted(project_id):", "    for gone in []:"],
            ["no-purge", "    store.purge_expired(project_id)\n", "    pass\n"],
            ["profile-any-role", '    if not await _has_capture_role():\n        return ("NOT SAVED', '    if False:\n        return ("NOT SAVED'],
            ["no-start-audit", '        await _audit("modernization.baseline_capture_started", capture_id,',
             '        (lambda *a: None)("modernization.baseline_capture_started", capture_id,'],
            ["no-profile-audit", '    await _audit("modernization.capture_profile_saved", "", {',
             '    (lambda *a: None)("modernization.capture_profile_saved", "", {'],
            ["failed-recorded", '    if manifest.get("status") != "complete":', "    if False:"],
            ["old-plan-ok", '    if plan.version != manifest.get("planVersion"):', "    if False:"],
            ["proposals-unchecked", "    if problems:\n        return _problems_text(\"NOT RECORDED YET — the baseline",
             "    if False:\n        return _problems_text(\"NOT RECORDED YET — the baseline"],
            ["not-kept", '    manifest["keep"] = True', '    manifest["keep"] = False'],
            ["no-freeze", "    version = await freeze_version(STAGE, artifact)", "    version = None"],
        ],
    },
    "spec_g_ledger.json": {
        "target": "shared/services/modernization_ledger.py",
        "tests": [f"{T}/test_record_approval.py"], **DB,
        "mutants": [
            ["unknown-module-ok", '            raise LedgerRefused(f"{p[\'module_id\']} is not on the ledger — approve its design and plan first")',
             "            continue"],
            ["blocked-ok", "        if row.state == \"blocked\":\n            raise LedgerRefused(f\"{p['module_id']} is blocked ({row.blocked_reason}); unblock it before baselining it\")",
             "        if False:\n            raise LedgerRefused(f\"{p['module_id']} is blocked ({row.blocked_reason}); unblock it before baselining it\")"],
            ["migrating-rebaselined", '        if row.state not in ("sequenced", "baselined") and sorted(row.baseline_ids or []) != sorted(p["baseline_ids"]):',
             "        if False:"],
            ["revision-unrecorded", 'actor=actor, artifact=artifact, note="baseline revised")]', "actor=actor, artifact=artifact)]"],
        ],
    },
    "spec_g_route.json": {
        "target": "shared/routers/artifact_versions.py",
        "tests": [f"{T}/test_record_approval.py"], **DB,
        "mutants": [
            ["acceptance-skips-ledger", '    elif stage == "testing_modernization":\n        await _baseline_approved',
             '    elif False:\n        await _baseline_approved'],
            ["no-placements-accepted", "    if not placements:\n        raise HTTPException(status_code=409, detail=(\n            \"Not accepted",
             "    if False:\n        raise HTTPException(status_code=409, detail=(\n            \"Not accepted"],
        ],
    },
    "spec_g_ui.json": {
        "root": "frontend", "target": "components/modernization/equivalence-view.tsx",
        "cmd": ["node", "node_modules/vitest/vitest.mjs", "run", "__tests__/app/equivalence-page.test.tsx"],
        "mutants": [
            ["ledger-claims-rejected", '  if (status === "rejected") return', "  if (false) return"],
            ["ledger-no-refetch", "    if (approved) void refetch();", "    if (false) void refetch();"],
            ["unhandled-hidden", "                    ) : isProposed ? (", "                    ) : true ? ("],
            ["proposed-as-covered", "                    {covered ? (", "                    {covered || isProposed ? ("],
            ["failed-looks-fine", '        {c.status === "failed" && <Badge variant="danger" className="font-normal">failed — nothing recorded, nothing accepted</Badge>}',
             ""],
            ["running-not-polled", '    refetchInterval: (query) => (query.state.data?.captures.some((c) => c.status === "running") ? 5000 : false),',
             "    refetchInterval: false,"],
            ["examples-hidden", "{s.examples[f] && <span className=\"text-muted-foreground\"> — {s.examples[f][0]} vs {s.examples[f][1]}</span>}", ""],
        ],
    },
}

LC = f"{T}/test_lifecycle.py"
SPECS["spec_g_lifecycle_store.json"] = {
    "target": "agents_orchestrator/testing_modernization_agent/store.py",
    "tests": [LC],
    "mutants": [
        ["lock-not-exclusive", "os.O_CREAT | os.O_EXCL | os.O_WRONLY", "os.O_CREAT | os.O_WRONLY"],
        ["stale-lock-held-forever", '                if held and datetime.fromisoformat(held["at"]) + timedelta(seconds=max_capture_seconds()) > now:',
         "                if held:"],
        ["release-anyones-lock", '        if held is not None and held.get("capture") == capture_id:', "        if held is not None:"],
        ["reap-fresh", "            if started + timedelta(seconds=max_capture_seconds()) > now:\n                continue",
         "            if False:\n                continue"],
        ["reap-complete", '            if m.get("status") != "running":', "            if False:"],
        ["reap-keeps-partial", '            for sub in ("run1", "run2"):\n                shutil.rmtree(self.capture_dir(project_id, m["id"]) / sub',
         '            for sub in ():\n                shutil.rmtree(self.capture_dir(project_id, m["id"]) / sub'],
        ["not-a-project-swept", "            except ValueError:\n                continue\n    return sorted(out)",
         "            except ValueError:\n                out.append(d.name)\n    return sorted(out)"],
    ],
}
SPECS["spec_g_lifecycle_runner.json"] = {
    "target": "agents_orchestrator/testing_modernization_agent/sandbox/runner.py",
    "tests": [LC],
    "mutants": [
        ["caps-kept", '    return ["--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", memory,',
         '    return ["--memory", memory,'],
        ["app-unlimited", '               *self._labels(), *limits(), "--read-only", "--tmpfs", "/tmp:rw",',
         '               *self._labels(), "--read-only", "--tmpfs", "/tmp:rw",'],
        ["cancel-ignored", "        if cancelled is not None and cancelled.is_set():", "        if False:"],
        ["no-check-between-scenarios", "                    _check()\n                    recorded.append", "                    recorded.append"],
    ],
}
SPECS["spec_g_lifecycle_sweeper.json"] = {
    "target": "workers/baseline_retention_sweeper.py",
    "tests": [LC],
    "mutants": [
        ["no-docker-cleanup", "                for capture_id in gone:\n                    runner.cleanup(capture_id)",
         "                for capture_id in []:\n                    runner.cleanup(capture_id)"],
        ["one-failure-stops-all", '                logger.exception("baseline retention: sweeping project %s failed", project_id)',
         "                raise"],
        ["no-purge", "                purged += store.purge_expired(project_id, now)", "                pass"],
    ],
}
SPECS["spec_g_strategy_proposals.json"] = {
    "target": "agents_orchestrator/strategy_agent/tools/strategy_tools.py",
    "tests": [LC],
    "mutants": [
        ["always-open", '"in_plan": rule is not None', '"in_plan": False'],
        ["always-covered", '"in_plan": rule is not None', '"in_plan": True'],
        ["any-criterion-covers", '        rules = (ecs.get(p.get("ec_id")) or {}).get("normalization") or []',
         '        rules = [r for c in ecs.values() for r in c.get("normalization") or []]'],
    ],
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(name, len(spec["mutants"]))
