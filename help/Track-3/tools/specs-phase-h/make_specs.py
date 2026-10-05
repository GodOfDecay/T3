"""Writes the Phase H mutation specs (R46): Migration Development.

    python help/Track-3/tools/specs-phase-h/make_specs.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
T = "tests/development_modernization"
A = "agents_orchestrator/development_modernization_agent"
DB = {"env_test": True}

SPECS = {
    "spec_h_rules.json": {
        "target": f"{A}/rules.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["other-module-ok", "    if in_module(path, module_path) or is_shared_build_file(path):", "    if True:"],
            ["any-build-file-shared", '    return "/" not in path and any(fnmatch.fnmatchcase(path, p) for p in SHARED_ROOT)',
             "    return is_build_file(path)"],
            ["prefix-match", '    return path == root or path.startswith(root + "/")', "    return path.startswith(root)"],
            ["dotdot-ok", '    if norm == "." or norm.startswith("../") or norm == ".." or "/../" in f"/{norm}/":', '    if norm == ".":'],
            ["absolute-ok", '    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):', "    if not raw:"],
            ["git-dir-ok", '    if norm == ".git" or norm.startswith(".git/"):', "    if False:"],
            ["private-key-unseen", '    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),', ""],
            ["password-unseen", '    ("a connection string with a password", re.compile(',
             '    ("a connection string with a password", re.compile(r"(?!x)x") or re.compile('],
            ["env-reference-is-secret", r'''(?![\"']?\s*(?:\$\{|\{\{|%\(|<|os\.environ|getenv|env\[|kv://|vault:))''', ""],
            ["build-unclassified", "    return any(fnmatch.fnmatchcase(name, p) for p in BUILD_NAMES) or any(path.startswith(d) for d in BUILD_DIRS)",
             "    return False"],
        ],
    },
    "spec_h_record.json": {
        "target": f"{A}/record.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["incomplete-map-ok", "    if missing:\n        problems.append(\"The file map does not cover", "    if False:\n        problems.append(\"The file map does not cover"],
            ["ghost-entries-ok", "    if extra:\n", "    if False:\n"],
            ["missing-target-ok", '        if e.get("disposition") in ("mapped", "merged") and e.get("target_path") and e["target_path"] not in target:',
             "        if False:"],
            ["outside-diff-ok", "    if outside:\n        problems.append(\"The branch changes files outside", "    if False:\n        problems.append(\"The branch changes files outside"],
            ["rewrite-claim-ok", '        if r.get("file") not in set(changed):', "        if False:"],
            ["secret-ok", "    for hit_file, kinds in sorted(secret_hits.items()):", "    for hit_file, kinds in []:"],
            ["vault-anything", '        if not _VAULT_RE.match(str(ref).strip()):', "        if False:"],
            ["unknown-trap-ok", "    if unknown:\n", "    if False:\n"],
            ["unhandled-trap-ok", "        if unhandled:\n", "        if False:\n"],
            ["red-build-ready", '        if build["status"] != "green":', "        if False:"],
            ["red-check-ok", '            if result and result.get("status") == "red":', "            if False:"],
            ["stale-check-ok", '            if result and state.get("builds") and result.get("head") != state["builds"][-1].get("head"):', "            if False:"],
            ["stale-build-ok", '        if not state.get("builds") or state["builds"][-1].get("head") != state.get("head"):', "        if False:"],
            ["pending-ok", "    if list(pending):", "    if False:"],
            ["blocked-with-code", "        if changed:\n", "        if False:\n"],
            ["rounds-uncapped", '"rounds": min(len(builds), 5)', '"rounds": len(builds)'],
            ["green-from-first", '    last = builds[-1]', '    last = builds[0]'],
        ],
    },
    "spec_h_workspace.json": {
        "target": f"{A}/workspace.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["forced-push", '    git(repo, "push", "--porcelain", url, *refs, secret=secret)', '    git(repo, "push", "--force", "--porcelain", url, *refs, secret=secret)'],
            ["dirty-push", '    if pending(repo):\n        raise WorkspaceError("There are uncommitted changes; commit them', '    if False:\n        raise WorkspaceError("There are uncommitted changes; commit them'],
            ["mixed-commit", '    take = changed if include_build else (build if concern == "build" else code)', "    take = changed"],
            ["any-concern", "    if concern not in CONCERNS:", "    if False:"],
            ["first-file-lost", "    out = git(repo, \"status\", \"--porcelain\", \"-z\", \"--no-renames\", \"--untracked-files=all\", raw=True)",
             "    out = git(repo, \"status\", \"--porcelain\", \"-z\", \"--no-renames\", \"--untracked-files=all\")"],
            ["no-copy-commit", '        commit(repo, state, "copy", f"Copy', '        (lambda *a, **k: None)(repo, state, "copy", f"Copy'],
            ["overwrite-target", '        if target.exists():\n            raise WorkspaceError', '        if False:\n            raise WorkspaceError'],
            ["no-empty-base", "        created_base = True", "        created_base = False"],
            ["credential-kept", '    git(repo, "remote", "set-url", "origin", clean_url)', "    pass"],
            ["secret-in-error", "scrub((proc.stderr or proc.stdout).strip(), secret)", "(proc.stderr or proc.stdout).strip()"],
            ["lock-shared", "            if fresh:\n                return False", "            if False:\n                return False"],
            ["release-anyones", '        if json.loads(path.read_text(encoding="utf-8")).get("holder") == holder:', "        if True:"],
            ["bad-module-id", '    if not _MODULE_RE.match(module_id or ""):', "    if False:"],
        ],
    },
    "spec_h_remote.json": {
        "target": f"{A}/remote.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["map-in-production", '    return os.environ.get("ENV", "").strip().lower() in ("dev", "test")', "    return True"],
            ["credential-without-tenant", '        auth = await conn.auth_adapter(str(get_tenant_id() or ""))', "        auth = await conn.auth_adapter()"],
            ["token-sent-to-other-host", "    if provider != target.kind:", "    if False:"],
        ],
    },
    "spec_h_legacy_credential.json": {
        "target": "agents_orchestrator/discovery_agent/tools/repo_tools.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["legacy-credential-without-tenant", '        auth = await conn.auth_adapter(str(get_tenant_id() or ""))', "        auth = await conn.auth_adapter()"],
        ],
    },
    "spec_h_toolchains.json": {
        "target": f"{A}/toolchains.py", "tests": [f"{T}/test_units.py"],
        "mutants": [
            ["unpinned-image-ok", "    if not DIGEST_RE.search(image):", "    if False:"],
        ],
    },
    "spec_h_sandbox.json": {
        "target": f"{A}/sandbox.py", "tests": [f"{T}/test_sandbox.py"],
        "mutants": [
            ["network-on", '    args = ["run", "--rm", "--network", "none", *limits(),', '    args = ["run", "--rm", *limits(),'],
            ["build-writes", '    mount = f"type=bind,src={workspace.resolve()},dst=/work" + ("" if writable else ",readonly")',
             '    mount = f"type=bind,src={workspace.resolve()},dst=/work"'],
            ["not-redacted", "    return CommandResult(exit_code=proc.returncode, output=sanitize_output(out.strip()),",
             "    return CommandResult(exit_code=proc.returncode, output=out.strip(),"],
        ],
    },
    "spec_h_build_check.json": {
        "target": f"{A}/checks/python_build.py", "tests": [f"{T}/test_sandbox.py"],
        "mutants": [
            ["imports-unchecked", "                if not found:\n", "                if False:\n"],
            ["always-green", "    return 1 if errors else 0", "    return 0"],
        ],
    },
    "spec_h_tools.json": {
        "target": f"{A}/tools/migration_tools.py", "tests": [f"{T}/test_chain.py"], **DB,
        "mutants": [
            ["orchestrator-migrates", "    if get_orchestrator_run():\n        return (\"Modules are migrated", "    if False:\n        return (\"Modules are migrated"],
            ["any-role", "    if not (await _roles()) & DEV_ROLES:", "    if False:"],
            ["no-baseline-ok", '    if not item["baseline_accepted"]:\n        return (f"Not yet:', '    if False:\n        return (f"Not yet:'],
            ["manual-migrated", '    if item["tier"] == "manual":\n        return (f"{module_id} is MANUAL tier', '    if False:\n        return (f"{module_id} is MANUAL tier'],
            ["wave-ignored", '    if item["wave_starts"] and item["wave_starts"] > today and not override_wave_order and item["state"] == "baselined":',
             "    if False:"],
            ["no-target-ok", '    if row is None:\n        raise RemoteError("No target repository', '    if False:\n        raise RemoteError("No target repository'],
            ["ledger-not-moved", "            async with get_db_session_for_tenant(tenant) as db:\n                await ledger.migration_started(",
             "            async with get_db_session_for_tenant(tenant) as db:\n                0 and ledger.migration_started("],
            ["secret-written", "    if kinds:\n        raise rules.WriteRefused(f\"NOT WRITTEN", "    if False:\n        raise rules.WriteRefused(f\"NOT WRITTEN"],
            ["outside-written", "    rel = rules.assert_may_write(path, state[\"module_path\"])\n    if len(content", "    rel = rules.clean_path(path)\n    if len(content"],
            ["build-on-dirty", "        if W.pending(repo):\n            return \"There are uncommitted changes; commit them first (fix for code",
             "        if False:\n            return \"There are uncommitted changes; commit them first (fix for code"],
            ["rounds-uncapped", '        if kind == "build" and len(builds) >= MAX_ROUNDS:', "        if False:"],
            ["preview-unmasked-name", '            reason = str(exc).replace("The legacy service", "The service with the migrated module")', "            reason = str(exc)"],
            ["record-unchecked", "    if problems:\n        return \"NOT RECORDED — \" + \"\\n\".join(f\"- {p}\" for p in problems[:14])",
             "    if False:\n        return \"NOT RECORDED — \" + \"\\n\".join(f\"- {p}\" for p in problems[:14])"],
            ["blocked-not-on-ledger", "                await ledger.block(db, project_id=project, module_id=module_id, agent=STAGE,",
             "                0 and ledger.block(db, project_id=project, module_id=module_id, agent=STAGE,"],
            ["no-consent", "    if not ok:\n        return why\n    state, mdir, why = _open_state(module_id)\n    if state is None:\n        return why\n    row = await _newest_record",
             "    state, mdir, why = _open_state(module_id)\n    if state is None:\n        return why\n    row = await _newest_record"],
            ["unaccepted-pushed", '    if row.status not in ("published", "granted"):', "    if False:"],
            ["changed-pushed", '    if W.pending(repo) or W.head(repo) != record.get("head_sha"):', "    if False:"],
            ["no-write-guard", "            await rr.assert_target_write(db, tenant_id=tenant, project_id=project, stage=STAGE, remote_url=target.url)",
             "            pass"],
            ["not-migrating-pushed", '        if rows.get(module_id, {}).get("state") != "migrating":', "        if False:"],
            ["ledger-not-in-review", "            await ledger.pr_opened(db, project_id=project, module_id=module_id, pr_url=pr_url, actor=user or None,",
             "            0 and ledger.pr_opened(db, project_id=project, module_id=module_id, pr_url=pr_url, actor=user or None,"],
            ["no-push-audit", '    await _audit("modernization.migration_pushed"', '    (lambda *a: None)("modernization.migration_pushed"'],
        ],
    },
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(name, len(spec["mutants"]))
