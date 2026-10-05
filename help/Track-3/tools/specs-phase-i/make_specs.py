"""Writes the Phase I mutation specs (R46): Migration Review and Security (Modernization).

    python help/Track-3/tools/specs-phase-i/make_specs.py
    cd backend && for s in ../help/Track-3/tools/specs-phase-i/spec_i_*.json; do .venv/bin/python ../help/Track-3/tools/mutate.py $s; done
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
T = "tests/review_security_modernization"
R = "agents_orchestrator/code_review_modernization_agent"
S = "agents_orchestrator/security_modernization_agent"
C = "agents_orchestrator/modernization_common"
UNIT = [f"{T}/test_units.py"]

SPECS = {
    "spec_i_analysis.json": {
        "target": f"{R}/analysis.py", "tests": UNIT,
        "mutants": [
            ["private-functions-public", '            if (m := _DEF.match(line)) and not m.group(1).startswith("_"):',
             "            if (m := _DEF.match(line)):"],
            ["no-status", "        for m in _STATUS.finditer(line):\n            add(\"status\", m.group(1))", "        for m in []:\n            add(\"status\", m.group(1))"],
            ["no-path-eq", "        for m in _PATH_EQ.finditer(line):", "        for m in []:"],
            ["sql-double-only", "            add(\"sql\", _norm(m.group(1) or m.group(2)))", "            add(\"sql\", _norm(m.group(1) or \"\"))"],
            ["no-encoding", "        for m in _ENCODING.finditer(line):", "        for m in []:"],
            ["no-file-write", "        for m in _OPEN_WRITE.finditer(line):", "        for m in []:"],
            ["no-phase-e-inventory", "    if top.is_dir():\n        inv = capture_interfaces(top)", "    if False:\n        inv = capture_interfaces(top)"],
            ["moved-file-not-followed", "            legacy_path = path if change == \"removed\" else back.get(path, path)",
             "            legacy_path = path"],
            ["added-not-tied", "    for change, items in ((\"removed\", removed), (\"added\", added)):", "    for change, items in ((\"removed\", removed),):"],
            ["contract-path-with-line", '        path = loc.split(":", 1)[0].strip().lstrip("/")', '        path = loc.strip().lstrip("/")'],
            ["comments-scanned", '            if line.lstrip().startswith(("#", "//")) and not line.lstrip().startswith("#!"):', "            if False:"],
            ["suffix-ignored", "                if suffixes and suffix not in suffixes:", "                if False:"],
            ["carried-by-name-only", "        counterpart = back.get(h[\"file\"], h[\"file\"])", "        counterpart = h[\"file\"]"],
            ["nothing-fixed", "    fixed = [{**h, \"origin\": \"fixed\"} for h in legacy_hits if id(h) not in used]", "    fixed = []"],
            ["double-use", "            used.add(id(match))\n            target_out.append", "            target_out.append"],
            ["credential-word-boundary", r'''re.compile(r"""(?i)\b\w*(?:password|passwd|pwd|secret|api[_-]?key|token)\w*\s*[:=]''',
             r'''re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]'''],
            ["localhost-host", r'''(?!localhost|127\.0\.0\.1|example\.|[\w.-]*\.invalid)[\w.-]+""")),''', r'''[\w.-]+""")),'''],
        ],
    },
    "spec_i_review_checks.json": {
        "target": f"{R}/checks.py", "tests": UNIT,
        "mutants": [
            ["missing-ok", "        if missing := sorted(need - have):", "        if missing := []:"],
            ["unknown-ok", "        if unknown := sorted(x for x in have - need if x):", "        if unknown := []:"],
            ["traceability-ok", "    if missing := sorted(set(legacy_files) - tr):", "    if missing := []:"],
            ["ghost-files-ok", "    if extra := sorted(p for p in tr - set(legacy_files) if p):", "    if extra := []:"],
            ["nothing-read-ok", "    if not target_read:", "    if False:"],
            ["unread-target-ok", '        if f.get("file") and f["file"] not in target_read:', "        if False:"],
            ["unread-legacy-ok", '        if f.get("legacy_file") and f["legacy_file"] not in legacy_read:', "        if False:"],
            ["one-sided-ok", '        if f.get("category") in _COMPARING and not f.get("legacy_file"):', "        if False:"],
            ["where-optional", '        if t.get("status") == "handled" and not (t.get("where") or "").strip():', "        if False:"],
            ["diff-ignored", '        if bearing and entry and entry.get("status") == "unchanged" and not (entry.get("note") or "").strip():',
             "        if False:"],
            ["any-kind-bears", '        bearing = [c for c in changes if c.get("kind") in CONTRACT_KINDS]', "        bearing = list(changes)"],
        ],
    },
    "spec_i_compare.json": {
        "target": f"{S}/compare.py", "tests": UNIT,
        "mutants": [
            ["package-case", '        return ("dep", f.get("cve"), (f.get("package") or "").lower())', '        return ("dep", f.get("cve"), f.get("package") or "")'],
            ["secret-by-file", '    if f["tool"] == "gitleaks" and f.get("secret_hash"):', "    if False:"],
            ["no-file-map", '        key = _key(f, back.get(f.get("file") or "", f.get("file") or ""))', '        key = _key(f, f.get("file") or "")'],
            ["nothing-fixed", "             for f in legacy if id(f) not in used]", "             for f in []]"],
            ["reuse-match", "            used.add(id(match))\n            ref = ", "            ref = "],
            ["short-values", "        if not value or len(value) < 6:", "        if not value:"],
            ["no-url-passwords", "            for rx in (_CREDENTIAL, _URL_PASSWORD):", "            for rx in (_CREDENTIAL,):"],
            ["anonymous-ok", '    opened = "allow_anonymous" in tm and "allow_anonymous" not in lm', "    opened = False"],
            ["missing-markers-ok", "    if lset - tset or opened:", "    if opened:"],
            ["stricter-is-same", "    if tset - lset:", "    if False:"],
            ["vault-is-secret", r'''["'](?!kv://|vault:|keyvault:|secretsmanager:|env:|\$\{)([^"'\s]{6,})["']""")''', r'''["']([^"'\s]{6,})["']""")'''],
        ],
    },
    "spec_i_security_checks.json": {
        "target": f"{S}/checks.py", "tests": UNIT,
        "mutants": [
            ["late-ok", '        if late:\n', "        if False:\n"],
            ["highs-optional", "        if hit.get(\"severity\") not in _BLOCKING:\n            continue", "        if True:\n            continue"],
            ["origin-ignored", '        elif not any(f.get("origin") == hit.get("origin") for f in found):', "        elif False:"],
            ["cve-only", '        return bool(hit.get("cve")) and finding.get("cve") == hit["cve"] and \\\n            (finding.get("package") or "").lower() == (hit.get("package") or "").lower()',
             '        return finding.get("cve") == hit["cve"]'],
            ["carryover-ok", "    for c in carryover:", "    for c in []:"],
            ["carryover-any-severity", '                   and f.get("severity") == "critical" for f in findings):', "                   for f in findings):"],
            ["authz-coverage-ok", "    if missing := sorted(set(http_contracts) - set(stated)):", "    if missing := []:"],
            ["weaker-ok", '        if a and ev.get("suggested") == "weaker" and a.get("status") != "weaker" and not (a.get("note") or "").strip():',
             "        if False:"],
        ],
    },
    "spec_i_scanners.json": {
        "target": f"{S}/scanners.py", "tests": UNIT,
        "mutants": [
            ["unpinned-ok", '    if "@sha256:" not in ref:', "    if False:"],
            ["value-kept", '        out.append({"tool": "gitleaks", "rule": r.get("RuleID"), "cve": None,',
             '        out.append({"tool": "gitleaks", "Secret": value, "rule": r.get("RuleID"), "cve": None,'],
            ["secret-not-critical", '"title": f"Secret in code ({r.get(\'RuleID\')})", "severity": "critical",',
             '"title": f"Secret in code ({r.get(\'RuleID\')})", "severity": "high",'],
            ["semgrep-error-medium", '_SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}',
             '_SEMGREP_SEVERITY = {"ERROR": "medium", "WARNING": "medium", "INFO": "low"}'],
            ["sbom-counts-manifests", ' if c.get("type") != "application")', ")"],
            ["no-db-ran", "    if not trivy_db_ready():", "    if False:"],
            ["failed-is-ran", '        scans["semgrep"], notes["semgrep"] = "failed", str(exc)[:300]', '        scans["semgrep"], notes["semgrep"] = "ran", str(exc)[:300]'],
            ["module-prefix-lost", "        target = _rel(r.get(\"Target\") or \"\", module_path)", "        target = r.get(\"Target\") or \"\""],
        ],
    },
    "spec_i_checkout.json": {
        "target": f"{C}/review_checkout.py", "tests": UNIT,
        "mutants": [
            ["draft-reviewable", '    if row.status not in ("published", "granted"):', "    if False:"],
            ["failed-reviewable", '    if record.get("outcome") != "ready_for_review":', "    if False:"],
            ["headless-reviewable", '    if not record.get("head_sha") or not record.get("target_branch"):', "    if False:"],
            ["push-enabled", '    W.git(repo, "remote", "set-url", "--push", "origin", _DISABLED_PUSH_URL)', "    pass"],
            ["any-head", '    if W.git(repo, "cat-file", "-t", head, check=False) != "commit":', "    if False:"],
            ["branch-tip", '    W.git(repo, "checkout", "-q", "--detach", head)', "    pass"],
            ["escape-ok", "        path.relative_to(base.resolve())\n    except ValueError:\n        return None",
             "        path.relative_to(\"/\")\n    except ValueError:\n        return None"],
            ["git-readable", '    if not rel or ".git" in pathlib.PurePosixPath(rel).parts:', "    if not rel:"],
            ["bad-head-ok", '    if not _MODULE_RE.match(module_id or "") or not head.isalnum():', '    if not _MODULE_RE.match(module_id or ""):'],
        ],
    },
    "spec_i_security_tools.json": {
        "target": f"{S}/tools/security_tools.py", "tests": UNIT,
        "mutants": [
            ["policy-from-nothing", "            scans=dict(artifact.get(\"scans\") or {}),", "            scans={t: \"ran\" for t in S.SCANNERS},"],
            ["authz-not-counted", "            contract_authz=[ContractAuthz.model_validate(a) for a in artifact.get(\"contract_authz\") or []],",
             "            contract_authz=[],"],
        ],
    },
    "spec_i_chain.json": {
        "target": "shared/routers/artifact_versions.py", "tests": [f"{T}/test_chain.py"], "env_test": True,
        "pytest_args": ["-k", "faithful or broken"],
        "mutants": [
            ["no-hook", '    elif stage in ("code_review_modernization", "security_modernization"):\n        await _verdict_approved',
             '    elif False:\n        await _verdict_approved'],
            ["stale-accepted", '    if current is None or current.version != payload["migration_version"] \\\n            or (current.payload or {}).get("head_sha") != payload.get("head_sha"):',
             "    if current is None:"],
            ["wrong-column", '    verdict = payload.get("merge_recommendation" if review else "verdict")', '    verdict = payload.get("verdict" if review else "verdict")'],
        ],
    },
}

for name, spec in SPECS.items():
    (HERE / name).write_text(json.dumps({"root": "backend", **spec}, indent=1) + "\n", encoding="utf-8")
print(f"{len(SPECS)} specs, {sum(len(s['mutants']) for s in SPECS.values())} mutants")
