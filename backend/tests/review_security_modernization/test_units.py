"""Migration Review and Security (Phase I) — the pure parts: the API-surface diff, the anti-pattern pack and
its classification, the review's submit checks, the scanners' parsers, the legacy diff, the secret
carry-over, the contract-authz evidence, the security submit checks, the documents, and Track 1's
security prompt left byte for byte as it was (I12)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil

import pytest

from agents_orchestrator.code_review_modernization_agent import analysis as A
from agents_orchestrator.code_review_modernization_agent.checks import check as review_check
from agents_orchestrator.code_review_modernization_agent.review_document import review_markdown
from agents_orchestrator.modernization_common import review_checkout as RC
from agents_orchestrator.modernization_common.handover.packets import SecurityPayload
from agents_orchestrator.security_modernization_agent import compare as C
from agents_orchestrator.security_modernization_agent import scanners as S
from agents_orchestrator.security_modernization_agent.checks import check as security_check
from agents_orchestrator.security_modernization_agent.security_document import security_markdown
from tests.review_security_modernization import lite_i as L
from tests.testing_modernization import lite

pytestmark = pytest.mark.unit


def _files(base: pathlib.Path, module: str = "claims-api") -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in (base / module).rglob("*") if p.is_file())


@pytest.fixture
def target(tmp_path):
    shutil.copytree(lite.SAMPLE / "claims-api", tmp_path / "claims-api")
    (tmp_path / "claims-api" / "server.py").write_text(L.migrated_server(), encoding="utf-8")
    return tmp_path


def _diff(base):
    legacy = A.surface(lite.SAMPLE, "claims-api", _files(lite.SAMPLE))
    tgt = A.surface(base, "claims-api", _files(base))
    return A.compare_surfaces(legacy, tgt, file_map=L.FILE_MAP, contracts=L.design()["frozen_contracts"])


# ── API surface ─────────────────────────────────────────────────────────────

def test_the_legacy_surface_is_read_from_the_code_with_locations():
    s = {(i["kind"], i["name"]): i["location"] for i in A.surface(lite.SAMPLE, "claims-api", _files(lite.SAMPLE))}
    assert s[("http_path", "/health")] == "claims-api/server.py:59"
    assert ("http_path", "^/api/claims/([A-Z0-9-]+)/settle$") in s and ("http_method", "POST") in s
    assert {k[1] for k in s if k[0] == "status"} == {"200", "404", "409"}
    assert ("function", "payout(amount, rate)") in s and ("db_uses", "claims") in s
    assert ("sql", "UPDATE claims SET status = 'settled', payout = ? WHERE id = ?") in s
    assert not any(k[1].startswith("_") for k in s if k[0] == "function")


def test_a_faithful_migration_changes_no_route_status_or_sql(target):
    d = _diff(target)
    kinds = {(i["kind"], i["name"]) for i in d["removed"] + d["added"]}
    assert kinds == {("http_consumes", "urllib2.urlopen"), ("http_consumes", "urllib.request.urlopen"), ("encoding", "utf-8")}
    assert {c["kind"] for c in d["contracts"]["CT-01"]} == {"http_consumes", "encoding"}
    assert d["contracts"]["CT-02"] == []


def test_a_changed_status_and_an_added_route_are_found_and_tied_to_the_contract(target):
    (target / "claims-api" / "server.py").write_text(L.broken_server(), encoding="utf-8")
    d = _diff(target)
    assert ("status", "409") in {(i["kind"], i["name"]) for i in d["removed"]}
    assert {("status", "400"), ("http_path", "/metrics")} <= {(i["kind"], i["name"]) for i in d["added"]}
    ct = {(c["change"], c["kind"], c["name"]) for c in d["contracts"]["CT-01"]}
    assert ("removed", "status", "409") in ct and ("added", "http_path", "/metrics") in ct
    md = A.surface_markdown(d, "M-01")
    assert "CT-01: 6 change(s)" in md and "CT-02: no change found" in md


def test_a_moved_file_is_compared_with_its_counterpart(tmp_path):
    (tmp_path / "claims-api" / "app").mkdir(parents=True)
    (tmp_path / "claims-api" / "app" / "main.py").write_text(L.migrated_server().replace("409", "418"))
    fmap = [{"legacy_path": "claims-api/server.py", "disposition": "mapped", "target_path": "claims-api/app/main.py"}]
    d = A.compare_surfaces(A.surface(lite.SAMPLE, "claims-api", ["claims-api/server.py"]),
                           A.surface(tmp_path, "claims-api", ["claims-api/app/main.py"]),
                           file_map=fmap, contracts=L.design()["frozen_contracts"])
    names = {(c["change"], c["name"]) for c in d["contracts"]["CT-01"] if c["kind"] == "status"}
    assert names == {("removed", "409"), ("added", "418")}


def test_the_surface_reader_sees_sql_in_either_quote_and_file_writers():
    items = A._own_surface("m/x.py", 'c.execute("SELECT a FROM t WHERE b = \'x\'")\n'
                                     "c.execute('DELETE FROM t WHERE id = ?')\nf = open(p, \"wb\")\n"
                                     "line.encode('cp1252')\n")
    got = {(i["kind"], i["name"]) for i in items}
    assert {("sql", "SELECT a FROM t WHERE b = 'x'"), ("sql", "DELETE FROM t WHERE id = ?"), ("file_write", "wb"),
            ("encoding", "cp1252")} <= got


# ── anti-patterns ───────────────────────────────────────────────────────────

def test_the_rule_pack_flags_what_it_says_and_skips_comments():
    text = ("import urllib2\nprint 'x'\nexcept ValueError, e:\nexcept Exception: pass\n"
            "c.execute(\"SELECT * FROM t WHERE id = %s\" % cid)\npassword = 'hunter22'\n"
            "# password = 'commented1'\nfor k, v in d.iteritems(): pass\nURL = 'http://billing.corp:8080'\n")
    rules = [h["rule"] for h in A.antipatterns({"m/a.py": text})]
    assert rules.count("hardcoded-credential") == 1
    assert [h["rule"] for h in A.antipatterns({"m/b.py": "DB_PASSWORD = 'hunter22'\nclientSecret: 'abcd1234'\n"})] == \
        ["hardcoded-credential", "hardcoded-credential"]
    for r in ("py2-module", "py2-print", "py2-except-comma", "exception-swallowed", "sql-string-built",
              "py2-builtins", "hardcoded-host"):
        assert r in rules, r
    assert A.antipatterns({"m/A.java": "private static Map cache = new HashMap();\nstatic final int X = 1;\n"
                                       "import org.apache.log4j.Logger;\n"})[0]["rule"] == "static-mutable"
    assert {h["rule"] for h in A.antipatterns({"m/A.java": "import org.apache.log4j.Logger;"})} == {"log4j1"}
    assert A.antipatterns({"m/a.py": "x = 'localhost'\nURL='http://localhost:8080'\n"}) == []
    assert A.antipatterns({"m/a.tsx": "$scope.items = []"})[0]["rule"] == "angularjs-scope"


def test_hits_are_carried_over_introduced_or_fixed_through_the_file_map():
    legacy = A.antipatterns({"m/old.py": "import urllib2\nURL = 'http://billing.corp'\n"})
    target = A.antipatterns({"m/new.py": "URL = 'http://billing.corp'\nc.execute('SELECT ' + x)\n"})
    fmap = [{"legacy_path": "m/old.py", "disposition": "mapped", "target_path": "m/new.py"}]
    r = A.classify(legacy, target, fmap)
    by_rule = {h["rule"]: h for h in r["target"]}
    assert by_rule["hardcoded-host"]["origin"] == "carried_over" and by_rule["hardcoded-host"]["legacy_file"] == "m/old.py"
    assert by_rule["sql-string-built"]["origin"] == "introduced"
    assert [h["rule"] for h in r["fixed"]] == ["py2-module"]
    # Without the map the same file name is the counterpart; another name is not.
    assert A.classify(legacy, target, [])["target"][0]["origin"] == "introduced"
    md = A.antipatterns_markdown(r, "M-01")
    assert "1 introduced, 1 carried over), 1 fixed" in md


def test_the_migrated_sample_carries_over_one_host_and_fixes_both_python2_imports(target):
    r = A.classify(A.antipatterns(A.module_texts(lite.SAMPLE, _files(lite.SAMPLE))),
                   A.antipatterns(A.module_texts(target, _files(target))), L.FILE_MAP)
    assert [(h["rule"], h["origin"]) for h in r["target"]] == [("hardcoded-host", "carried_over")]
    assert sorted(h["code"] for h in r["fixed"]) == ["import BaseHTTPServer", "import urllib2"]


# ── the review's submit checks ──────────────────────────────────────────────

CTX = {"contracts": [{"id": "CT-01", "kind": "http", "legacy_location": "claims-api/server.py:58"}],
       "traps": [{"id": "TR-01"}, {"id": "TR-02"}], "criteria": [{"id": "EC-01"}, {"id": "EC-02"}, {"id": "EC-04"}]}
LEGACY_FILES = ["claims-api/requirements.txt", "claims-api/runtime.txt", "claims-api/server.py"]
OPENED = {"target": ["claims-api/server.py"], "legacy": ["claims-api/server.py"]}


def _review(**over):
    r = {"findings": [], "contract_check": [{"ct_id": "CT-01", "status": "unchanged", "note": "bytes only"}],
         "trap_check": [{"tr_id": "TR-01", "status": "handled", "where": "claims-api/server.py:29"},
                        {"tr_id": "TR-02", "status": "handled", "where": "claims-api/server.py:53"}],
         "equivalence_coverage": [{"ec_id": e, "status": "covered"} for e in ("EC-01", "EC-02", "EC-04")],
         "traceability": [{"legacy_path": f, "target_path": f, "status": "mapped"} for f in LEGACY_FILES]}
    r.update(over)
    return r


def _rcheck(review, opened=OPENED, surface=None):
    return review_check(review=review, ctx=CTX, record={}, opened=opened, surface=surface or {"contracts": {}},
                        legacy_files=LEGACY_FILES)


def test_a_complete_honest_review_passes():
    assert _rcheck(_review()) == []


def test_every_contract_trap_criterion_and_legacy_file_must_be_answered():
    problems = _rcheck(_review(contract_check=[], trap_check=[{"tr_id": "TR-01", "status": "handled", "where": "x:1"},
                                                               {"tr_id": "TR-09", "status": "handled", "where": "x"}],
                               equivalence_coverage=[], traceability=[{"legacy_path": "claims-api/nope.py", "status": "missing"}]))
    text = "\n".join(problems)
    assert "frozen contract of the module needs a check; missing: CT-01" in text
    assert "trap of the module needs a check; missing: TR-02" in text and "does not have: TR-09" in text
    assert "missing: EC-01, EC-02, EC-04" in text
    assert "Traceability must cover every legacy file" in text and "does not have: claims-api/nope.py" in text


def test_a_finding_on_a_file_not_opened_is_refused_and_a_comparison_needs_the_legacy_line():
    f = {"id": "F-001", "severity": "high", "category": "behaviour_change", "file": "claims-api/other.py",
         "description": "d", "recommendation": "r"}
    text = "\n".join(_rcheck(_review(findings=[f])))
    assert "cites claims-api/other.py, which this review did not open" in text
    assert "cite the legacy file and line too" in text
    f2 = {**f, "file": "claims-api/server.py", "legacy_file": "claims-api/runtime.txt"}
    assert "cites legacy claims-api/runtime.txt, which this review did not open" in "\n".join(_rcheck(_review(findings=[f2])))
    assert "No migrated file was opened" in "\n".join(_rcheck(_review(), opened={"target": [], "legacy": []}))


def test_a_handled_trap_says_where():
    r = _review(trap_check=[{"tr_id": "TR-01", "status": "handled", "where": ""},
                            {"tr_id": "TR-02", "status": "not_applicable", "where": ""}])
    assert _rcheck(r) == ["TR-01 is handled — say where (file:line)."]


def test_a_contract_whose_file_changed_is_not_unchanged_without_a_reason():
    surface = {"contracts": {"CT-01": [{"change": "removed", "kind": "status", "name": "409"},
                                       {"change": "added", "kind": "http_consumes", "name": "urllib.request.urlopen"}]}}
    bare = _review(contract_check=[{"ct_id": "CT-01", "status": "unchanged", "note": ""}])
    assert any("CT-01 is marked unchanged, but its file changed: removed status `409`" in p for p in _rcheck(bare, surface=surface))
    assert _rcheck(_review(), surface=surface) == []  # a note explains it
    only_imports = {"contracts": {"CT-01": [{"change": "added", "kind": "http_consumes", "name": "x"}]}}
    assert _rcheck(bare, surface=only_imports) == []  # not a contract-bearing change


# ── scanners: parsers ───────────────────────────────────────────────────────

def test_trivy_semgrep_and_gitleaks_output_is_normalized_and_secrets_are_hashed():
    trivy = json.dumps({"Results": [{"Target": "requirements.txt", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2018-18074", "PkgName": "requests", "InstalledVersion": "2.19.0", "Severity": "HIGH",
         "FixedVersion": "2.20.0", "Title": "requests: redirect"}]}]})
    v = S.parse_trivy(trivy, "mod")[0]
    assert (v["cve"], v["package"], v["severity"], v["file"], v["fixed_version"]) == \
        ("CVE-2018-18074", "requests", "high", "mod/requirements.txt", "2.20.0")
    sem, errors = S.parse_semgrep(json.dumps({"results": [{"check_id": "rules.py-shell-true", "path": "/scan/mod/a.py",
                                                           "start": {"line": 5}, "extra": {"severity": "WARNING", "message": "m"}}],
                                              "errors": [{"message": "parse error"}]}))
    assert (sem[0]["rule"], sem[0]["severity"], sem[0]["file"], sem[0]["line"]) == ("py-shell-true", "medium", "mod/a.py", 5)
    assert errors == ["parse error"]
    leaks, values = S.parse_gitleaks(json.dumps([{"RuleID": "aws-access-token", "Secret": "AKIAIOSFODNN7EXAMPLQ",
                                                  "Match": "AKIAIOSFODNN7EXAMPLQ", "File": "/scan/mod/a.py", "StartLine": 2}]))
    assert values == ["AKIAIOSFODNN7EXAMPLQ"] and leaks[0]["severity"] == "critical"
    assert "AKIAIOSFODNN7EXAMPLQ" not in json.dumps(leaks) and leaks[0]["secret_hash"] == S.secret_hash("AKIAIOSFODNN7EXAMPLQ")
    assert S.parse_sbom(json.dumps({"components": [{"type": "library"}, {"type": "library"},
                                                    {"type": "application", "name": "requirements.txt"}]})) == 2


def test_an_image_must_be_pinned_by_digest(monkeypatch):
    assert "@sha256:" in S.image("trivy")
    monkeypatch.setenv("SDLC_SCANNER_IMAGE_SEMGREP", "semgrep/semgrep:latest")
    with pytest.raises(S.ScannerUnavailable, match="not pinned by digest"):
        S.image("semgrep")


def test_without_its_database_trivy_is_not_installed_and_says_how_to_fill_it(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_TRIVY_CACHE", str(tmp_path / "none"))
    (tmp_path / "m").mkdir()
    monkeypatch.setattr(S, "_run", lambda tool, *a, **k: "[]" if tool == "gitleaks" else json.dumps({"results": []}))
    r = S.scan(tmp_path, "m")
    assert r["scans"] == {"trivy": "not_installed", "semgrep": "ran", "gitleaks": "ran"}
    assert "--download-db-only" in r["notes"]["trivy"] and r["sbom"] == {"components": None, "vulnerabilities": None}


def test_a_scanner_that_fails_is_failed_not_clean(monkeypatch, tmp_path):
    (tmp_path / "m").mkdir()
    monkeypatch.setenv("SDLC_TRIVY_CACHE", str(tmp_path / "none"))

    def boom(tool, *a, **k):
        raise S.ScannerUnavailable(f"{tool} could not run: no")
    monkeypatch.setattr(S, "_run", boom)
    r = S.scan(tmp_path, "m")
    assert r["scans"]["semgrep"] == "failed" and r["scans"]["gitleaks"] == "failed" and r["findings"] == []


# ── security: the legacy diff, carry-over, authz ───────────────────────────

def _hit(tool, **kw):
    return {"tool": tool, "rule": kw.pop("rule", None), "cve": None, "package": None, "version": None, "file": None,
            "line": None, "secret_hash": None, "severity": "high", "title": "t", **kw}


def test_findings_are_matched_by_cve_package_rule_file_and_secret_hash():
    legacy = [_hit("trivy", cve="CVE-1", package="Requests", version="2.19.0", rule="CVE-1"),
              _hit("semgrep", rule="py-shell-true", file="m/old.py", line=3),
              _hit("gitleaks", rule="aws", file="m/old.py", line=1, secret_hash="abc"),
              _hit("trivy", cve="CVE-2", package="yaml", version="5.3", rule="CVE-2")]
    target = [_hit("trivy", cve="CVE-1", package="requests", version="2.20.0", rule="CVE-1"),
              _hit("semgrep", rule="py-shell-true", file="m/new.py", line=9),
              _hit("gitleaks", rule="aws", file="m/conf.py", line=4, secret_hash="abc"),
              _hit("semgrep", rule="py-eval-exec", file="m/new.py", line=2)]
    fmap = [{"legacy_path": "m/old.py", "disposition": "mapped", "target_path": "m/new.py"}]
    d = C.diff_findings(legacy, target, fmap)
    assert [f["origin"] for f in d["target"]] == ["carried_over", "carried_over", "carried_over", "introduced"]
    assert d["target"][0]["legacy_ref"] == "Requests@2.19.0" and d["target"][1]["legacy_ref"] == "m/old.py:3"
    assert [f["cve"] for f in d["fixed"]] == ["CVE-2"] and d["fixed"][0]["legacy_ref"] == "yaml@5.3"
    # Without the file map, a rule in a moved file is introduced (and the legacy one fixed).
    assert C.diff_findings(legacy, target, [])["target"][1]["origin"] == "introduced"


def test_a_legacy_secret_value_is_found_in_the_target_by_value_never_shown():
    legacy = C.credential_values({"m/old.py": "DB_PASSWORD = 's3cr3t-Value'\nURL='postgres://app:pa55word@db/x'\n"
                                              "pwd = '12'\n"})
    assert sorted(v for v, _f, _n in legacy) == ["pa55word", "s3cr3t-Value"]
    hits = C.secret_carryover(legacy + [("AKIAIOSFODNN7EXAMPLQ", "m/old.py", 9)],
                              {"m/new.py": "import os\nPASSWORD = os.environ['P']\n",
                               "m/cfg.ini": "[db]\npassword = s3cr3t-Value\n", "m/x.py": "k='AKIAIOSFODNN7EXAMPLQ'"})
    assert [(h["file"], h["line"], h["legacy_file"]) for h in hits] == [("m/cfg.ini", 2, "m/old.py"), ("m/x.py", 1, "m/old.py")]
    assert "s3cr3t-Value" not in json.dumps(hits) and "AKIA" not in json.dumps(hits)
    assert C.secret_carryover([("short", "f", 1)], {"m/a": "short"}) == []


def test_contract_authz_is_same_stricter_or_weaker_with_the_lines():
    legacy = "@login_required\ndef get():\n    if not has_role('adjuster'): abort(403)\n"
    assert C.contract_authz(legacy, legacy)["suggested"] == "same"
    weaker = C.contract_authz(legacy, "@login_required\ndef get(): pass\n")
    assert weaker["suggested"] == "weaker" and "role_check" in weaker["reason"]
    assert C.contract_authz(legacy, legacy + "token = jwt.decode(t)\n")["suggested"] == "stricter"
    opened = C.contract_authz(legacy, legacy + "@csrf_exempt\n")
    assert opened["suggested"] == "weaker" and "anonymous" in opened["reason"]
    none = C.contract_authz(L.LEGACY_SERVER, L.migrated_server())
    assert none["suggested"] == "same" and none["reason"] == "no authentication marker on either side"


# ── security: the submit checks and the packet's policy ────────────────────

def test_every_critical_or_high_target_hit_must_be_a_finding_with_its_computed_origin():
    hits = [{**_hit("trivy", cve="CVE-1", package="requests"), "origin": "carried_over"},
            {**_hit("semgrep", rule="py-eval-exec", file="m/a.py"), "origin": "introduced"},
            {**_hit("semgrep", rule="py-weak-hash", file="m/b.py", severity="medium"), "origin": "introduced"}]
    problems = security_check(report={"findings": []}, target_hits=hits, carryover=[], http_contracts=[], authz={})
    assert len(problems) == 2 and "CVE-1 in requests" in problems[0] and "m/a.py" in problems[1]
    wrong = {"findings": [{"cve": "CVE-1", "package": "requests", "origin": "introduced"},
                          {"file": "m/a.py", "origin": "introduced"}]}
    problems = security_check(report=wrong, target_hits=hits, carryover=[], http_contracts=[], authz={})
    assert problems == ["CVE-1 in requests is carried over (the legacy scan has it); its finding says otherwise."]


def test_a_carried_over_secret_must_be_a_critical_secret_finding_and_authz_covered():
    carry = [{"file": "m/x.py", "line": 1, "legacy_file": "m/old.py", "legacy_line": 9, "hash": "h"}]
    report = {"findings": [{"file": "m/x.py", "is_secret": True, "origin": "carried_over", "severity": "high"}],
              "contract_authz": [{"ct_id": "CT-01", "status": "same", "note": ""}]}
    problems = security_check(report=report, target_hits=[], carryover=carry, http_contracts=["CT-01", "CT-05"],
                              authz={"CT-01": {"suggested": "weaker", "reason": "the target lacks role_check"}})
    text = "\n".join(problems)
    assert "A legacy secret is in the target at m/x.py:1 (from m/old.py)" in text
    assert "missing: CT-05" in text and "CT-01's authorization is weaker (the target lacks role_check)" in text


def test_a_conditional_sign_off_remediates_inside_the_wave():
    report = {"verdict": "CONDITIONAL", "findings": [{"id": "S-001", "remediation_due": "2027-01-15"},
                                                     {"id": "S-002", "remediation_due": "2026-12-20"}]}
    assert security_check(report=report, target_hits=[], carryover=[], http_contracts=[], authz={},
                          wave_ends="2026-12-31") == [
        "CONDITIONAL needs every remediation inside the module's wave (it ends 2026-12-31); S-001 fall after it."]
    assert security_check(report={**report, "verdict": "FAIL"}, target_hits=[], carryover=[], http_contracts=[], authz={},
                          wave_ends="2026-12-31") == []


def _payload(**over):
    base = {"module_id": "M-01", "pr": "p", "legacy_commit": "c", "scans": {t: "ran" for t in S.SCANNERS},
            "verdict": "PASS", "rationale": "r"}
    base.update(over)
    return base


def test_the_policy_fails_reachable_or_unknown_high_and_never_passes_unscanned():
    hi = {"id": "S-001", "title": "t", "severity": "high", "origin": "carried_over", "legacy_ref": "x@1"}
    assert SecurityPayload.model_validate(_payload(findings=[hi], verdict="FAIL")).required_verdict() == "FAIL"
    with pytest.raises(ValueError, match="the policy gives FAIL"):
        SecurityPayload.model_validate(_payload(findings=[hi], verdict="CONDITIONAL"))
    unreachable = {**hi, "reachable": False, "remediation_plan": "upgrade", "remediation_due": "2026-12-01"}
    assert SecurityPayload.model_validate(_payload(findings=[unreachable], verdict="CONDITIONAL")).verdict == "CONDITIONAL"
    with pytest.raises(ValueError, match="trivy did not run"):
        SecurityPayload.model_validate(_payload(scans={"trivy": "not_installed", "semgrep": "ran", "gitleaks": "ran"}))


# ── documents ───────────────────────────────────────────────────────────────

def test_the_review_and_security_documents_say_what_was_decided():
    review = {"module_id": "M-01", "pr": "https://x/pull/1", "merge_recommendation": "request_changes", "summary": "s",
              "head_sha": "abcdef1234567", "migration_version": 2, "legacy_commit": "1234567890ab", "module": {"name": "claims-api"},
              "findings": [{"id": "F-001", "severity": "high", "category": "trap_unhandled", "file": "claims-api/server.py",
                            "line": 27, "legacy_file": "claims-api/server.py", "legacy_line": 27, "description": "round",
                            "recommendation": "Decimal"}],
              "trap_check": [{"tr_id": "TR-01", "status": "not_handled", "where": ""}],
              "files_read": {"target": ["a"], "legacy": ["a", "b"]}}
    md = review_markdown(review)
    assert "**Recommendation: Request changes**" in md and "Findings: 1 high" in md
    assert "| F-001 | high | trap unhandled | claims-api/server.py:27 | claims-api/server.py:27 |" in md
    assert "Files read: 1 target, 2 legacy" in md
    report = {"module_id": "M-01", "pr": "p", "verdict": "PASS", "rationale": "clean", "head_sha": "abc", "legacy_commit": "def",
              "scans": {"trivy": "ran", "semgrep": "ran", "gitleaks": "not_installed"}, "sbom": {"components": None},
              "fixed_from_legacy": [{"title": "py2-module", "legacy_ref": "claims-api/server.py:8"}], "findings": []}
    md = security_markdown(report)
    assert "**Verdict: PASS**" in md and "| gitleaks |  | not installed |" in md
    assert "SBOM: not generated; dependency vulnerabilities: not scanned." in md
    assert "0 introduced, 0 carried over, 1 fixed by the migration." in md


# ── the checkout's guards ──────────────────────────────────────────────────

def test_a_record_is_reviewable_only_when_ready_and_accepted():
    class Row:
        def __init__(self, status="published", **payload):
            self.version, self.status, self.payload = 3, status, payload
    ok = {"outcome": "ready_for_review", "head_sha": "a" * 40, "target_branch": "migrate/claims-api"}
    assert RC.refusal_for(Row(**ok), "M-01") is None
    assert RC.refusal_for(Row(status="granted", **ok), "M-01") is None
    assert "has no migration record" in RC.refusal_for(None, "M-01")
    assert "is not accepted yet" in RC.refusal_for(Row(status="draft", **ok), "M-01")
    assert "is blocked, not ready" in RC.refusal_for(Row(**{**ok, "outcome": "blocked"}), "M-01")
    assert "names no branch and head" in RC.refusal_for(Row(**{**ok, "head_sha": None}), "M-01")


def test_reads_never_leave_the_checkout(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret")
    assert RC.resolve(tmp_path, "a.py") == (tmp_path / "a.py").resolve()
    for bad in ("../etc/passwd", ".git/config", "", "nope.py"):
        assert RC.resolve(tmp_path, bad) is None, bad
    assert RC.resolve(None, "a.py") is None
    with pytest.raises(ValueError):
        RC.checkout_dir("00000000-0000-0000-0000-000000000001", "s", "M-01", "../x", base=tmp_path)


def test_a_clone_is_detached_at_the_accepted_head_with_push_disabled(tmp_path):
    import subprocess
    src = tmp_path / "src"
    src.mkdir()
    run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=src, check=True,
                                    capture_output=True, text=True).stdout.strip()
    run("init", "-q", "-b", "migrate/m")
    (src / "f").write_text("1")
    run("add", "-A")
    run("commit", "-q", "-m", "one")
    first = run("rev-parse", "HEAD")
    (src / "f").write_text("2")
    run("commit", "-qam", "two")
    repo = RC.clone_at(tmp_path / "co", git_url=str(src), branch="migrate/m", head=first)
    assert (repo / "f").read_text() == "1"
    push = subprocess.run(["git", "remote", "get-url", "--push", "origin"], cwd=repo, capture_output=True, text=True).stdout
    assert "push-disabled.invalid" in push
    assert RC.clone_at(tmp_path / "co", git_url=str(src), branch="migrate/m", head=first) == repo  # reused
    from agents_orchestrator.development_modernization_agent.workspace import WorkspaceError
    with pytest.raises(WorkspaceError, match="is not on migrate/m in the target any more"):
        RC.clone_at(tmp_path / "co2", git_url=str(src), branch="migrate/m", head="f" * 40)


# ── Track 1 untouched (I12) ────────────────────────────────────────────────

def test_track1_security_prompt_is_byte_for_byte_unchanged():
    from agents_orchestrator.security_agent.prompts.security_prompt import SECURITY_SYSTEM_PROMPT
    assert hashlib.sha256(SECURITY_SYSTEM_PROMPT.encode()).hexdigest() == \
        "243e33902ecd128cac0e77db60802a9de6bfcdbab16cd8204373e268f800a8e3"


def test_the_track3_prompts_state_the_policy_the_tools_enforce():
    from agents_orchestrator.code_review_modernization_agent.prompts.review_prompt import MIGRATION_REVIEW_SYS_MESSAGE as R
    from agents_orchestrator.security_modernization_agent.prompts.security_prompt import SECURITY_MODERNIZATION_SYS_MESSAGE as P
    assert "READ-ONLY on both repositories" in R and "files you opened are recorded" in R
    assert "never with a required scanner not run: not scanned is not clean" in P
    assert "AI analysis" not in P and "fall back" not in P.lower()
