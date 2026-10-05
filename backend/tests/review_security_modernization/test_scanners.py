"""The three scanners for real (Phase I, I7/I8): pinned images, offline, on a legacy module and its
migration — Trivy's dependency findings and SBOM, Semgrep's rules, Gitleaks' secrets (hashed) — and the
legacy diff that marks each carried over, introduced or fixed. Trivy needs its database
(`SDLC_TRIVY_CACHE`, filled once with network); without it, Trivy is `not_installed`, never clean."""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from agents_orchestrator.security_modernization_agent import compare as C
from agents_orchestrator.security_modernization_agent import scanners as S

needs_docker = pytest.mark.skipif(S.available() is not None, reason="Docker is not running")
_CACHE = os.environ.get("SDLC_TRIVY_CACHE") or "/tmp/claude-0/scan/trivy-cache"
needs_trivy_db = pytest.mark.skipif(not (pathlib.Path(_CACHE) / "db" / "trivy.db").is_file(),
                                    reason="Trivy's database is not on this machine")

LEGACY_APP = ("import subprocess, yaml\nAWS = 'AKIAIOSFODNN7EXAMPLQ'\n"
              "def run(cmd):\n    subprocess.call(cmd, shell=True)\n    return yaml.load(open('x'))\n")
TARGET_APP = ("import subprocess, yaml\nAWS = 'AKIAIOSFODNN7EXAMPLQ'\n"
              "def run(cmd):\n    subprocess.run(cmd, shell=True)\n    return yaml.safe_load(open('x'))\n"
              "def calc(expr):\n    return eval(expr)\n")


def _tree(root: pathlib.Path, reqs: str, app: str) -> pathlib.Path:
    (root / "mod").mkdir(parents=True)
    (root / "mod" / "requirements.txt").write_text(reqs)
    (root / "mod" / "app.py").write_text(app)
    return root


@needs_docker
@needs_trivy_db
def test_a_legacy_module_and_its_migration_are_scanned_and_diffed(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_TRIVY_CACHE", _CACHE)
    legacy = S.scan(_tree(tmp_path / "legacy", "requests==2.19.0\nPyYAML==5.3\n", LEGACY_APP), "mod", label="t-legacy")
    target = S.scan(_tree(tmp_path / "target", "requests==2.19.0\nPyYAML==6.0.1\n", TARGET_APP), "mod", label="t-target")
    for r in (legacy, target):
        assert r["scans"] == {"trivy": "ran", "semgrep": "ran", "gitleaks": "ran"}, r["notes"]
    assert legacy["sbom"]["components"] == 2 and legacy["sbom"]["vulnerabilities"] >= 7
    assert "AKIAIOSFODNN7EXAMPLQ" not in json.dumps({k: v for k, v in target.items() if k != "secret_values"})
    assert target["secret_values"] == ["AKIAIOSFODNN7EXAMPLQ"]

    d = C.diff_findings(legacy["findings"], target["findings"], [])
    origin = {(f["tool"], f.get("cve") or f["rule"]): f["origin"] for f in d["target"]}
    assert origin[("trivy", "CVE-2018-18074")] == "carried_over"          # requests 2.19.0 still there
    assert origin[("gitleaks", "aws-access-token")] == "carried_over"      # the same key, by hash
    assert origin[("semgrep", "py-shell-true")] == "carried_over"
    assert origin[("semgrep", "py-eval-exec")] == "introduced"
    fixed = {f.get("cve") or f["rule"] for f in d["fixed"]}
    assert {"CVE-2020-14343", "CVE-2020-1747", "py-unsafe-deserialization"} <= fixed   # PyYAML 5.3 and yaml.load gone


@needs_docker
def test_the_legacy_sample_scans_clean_of_secrets_and_dependencies(monkeypatch):
    from tests.testing_modernization import lite
    monkeypatch.setenv("SDLC_TRIVY_CACHE", _CACHE)
    r = S.scan(lite.SAMPLE, "claims-api", label="t-sample")
    assert r["scans"]["semgrep"] == "ran" and r["scans"]["gitleaks"] == "ran"
    assert [f for f in r["findings"] if f["tool"] != "semgrep"] == []
    assert {f["rule"] for f in r["findings"]} <= {"py-bind-all"}


@needs_docker
def test_without_the_database_trivy_is_not_installed_and_the_others_still_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_TRIVY_CACHE", str(tmp_path / "empty"))
    r = S.scan(_tree(tmp_path / "t", "requests==2.19.0\n", TARGET_APP), "mod")
    assert r["scans"] == {"trivy": "not_installed", "semgrep": "ran", "gitleaks": "ran"}
    assert r["sbom"] == {"components": None, "vulnerabilities": None}
