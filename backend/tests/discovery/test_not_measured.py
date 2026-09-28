"""R39 in Dependency and Risk: a vulnerability count nobody measured is never shown as 0.

Found in the Phase A audit (help/Track-3/build-log.md): with Trivy skipped or unavailable
the report's executive summary said "**0** known vulnerabilit(ies)" and every module's risk
score silently left the factor out.
"""
from __future__ import annotations

from datetime import date

import pytest

from agents_orchestrator.discovery_agent.analysis.assessment import (
    assess_repository,
    assessment_markdown,
)
from tests.discovery.legacy_fixture import build_legacy_repo

pytestmark = pytest.mark.unit

AS_OF = date(2026, 9, 10)
SUMMARY_ZERO = "**0** known vulnerabilit(ies)"


@pytest.fixture
def repo(tmp_path):
    return build_legacy_repo(tmp_path)


def _vuln_factor(module: dict) -> dict | None:
    return next((f for f in module["risk"]["factors"] if f["factor"] == "vulnerable_dependencies"), None)


@pytest.mark.parametrize("scanners", [None, {"trivy": "unavailable", "note": "not installed"},
                                      {"trivy": "error", "note": "TimeoutError"}])
def test_without_a_scan_the_summary_says_not_scanned(repo, scanners):
    md = assessment_markdown(assess_repository(repo, as_of=AS_OF, scanners=scanners))
    assert SUMMARY_ZERO not in md
    assert "known vulnerabilities **not scanned** (Trivy: " in md


def test_with_a_clean_scan_the_summary_says_zero(repo):
    md = assessment_markdown(assess_repository(repo, as_of=AS_OF, vulnerabilities=[],
                                               scanners={"trivy": "ok", "note": "0 finding(s)."}))
    assert SUMMARY_ZERO in md
    assert "not scanned" not in md


def test_without_a_scan_every_module_records_the_factor_as_not_measured(repo):
    modules = assess_repository(repo, as_of=AS_OF, scanners={"trivy": "unavailable"})["modules"]
    for m in modules:
        factor = _vuln_factor(m)
        assert factor is not None, m["name"]
        assert factor["measured"] is False and factor["points"] == 0
        assert factor["detail"].startswith("Not measured")


def test_with_a_scan_the_factor_scores_the_findings(repo):
    vulns = [{"package": "Newtonsoft.Json", "installed_version": "9.0.1", "severity": "high",
              "cve": "CVE-2024-21907", "target": "src/Billing.Web/packages.config"}]
    modules = assess_repository(repo, as_of=AS_OF, vulnerabilities=vulns,
                                scanners={"trivy": "ok"})["modules"]
    web = next(m for m in modules if m["name"] == "Billing.Web")
    factor = _vuln_factor(web)
    assert factor == {"factor": "vulnerable_dependencies", "points": 10,
                      "detail": "1 high/critical and 0 other known vulnerabilities."}
