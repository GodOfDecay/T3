"""Phase D — Dependency and Risk (research §6.2): stable M-xx ids, "Not assessable statically",
the golden-master pointer, and the hand-over packet. Pure: no database.

Guarding: ids are numbered by PATH (not by risk, which moves) and are identical across two runs
on the same checkout; the persist model keeps the new section (pydantic drops unknown keys); the
report has the ids and the section; the assessment emits a valid packet.
"""
from __future__ import annotations

from datetime import date

from agents_orchestrator.discovery_agent.analysis.assessment import (
    SCHEMA_VERSION, assess_repository, assessment_markdown,
)
from agents_orchestrator.modernization_common.handover.emit import assessment_packet
from shared.models.artifacts import DiscoveryArtifact
from tests.discovery.legacy_fixture import build_legacy_repo

AS_OF = date(2026, 9, 1)
REPO = {"url": "https://dev.azure.com/acme/billing/_git/billing", "commit": "a1b2c3d4", "name": "billing"}


def _assess(root):
    return assess_repository(build_legacy_repo(root) if not (root / "src").exists() else root,
                             as_of=AS_OF, repository=REPO)


def test_ids_are_minted_by_path_and_stable_across_runs(tmp_path):
    first = _assess(tmp_path)
    second = _assess(tmp_path)
    ids = {m["path"]: m["id"] for m in first["modules"]}
    assert ids == {m["path"]: m["id"] for m in second["modules"]}
    by_path = [ids[p] for p in sorted(ids)]
    assert by_path == [f"M-{n:02d}" for n in range(1, len(ids) + 1)]
    # The report still lists riskiest first — the ids do not follow that order.
    scores = [m["risk"]["score"] for m in first["modules"]]
    assert scores == sorted(scores, reverse=True)
    assert first["schema_version"] == SCHEMA_VERSION == 2


def test_the_new_sections_survive_the_persist_model(tmp_path):
    artifacts = _assess(tmp_path)
    assert artifacts["not_assessable_statically"], "the configuration question is always asked"
    assert artifacts["golden_master"] == {"status": "not_captured", "baselines": [],
                                          "note": artifacts["golden_master"]["note"]}
    assert "Equivalence Testing" in artifacts["golden_master"]["note"]
    kept = DiscoveryArtifact(**artifacts).model_dump()
    assert kept["not_assessable_statically"] == artifacts["not_assessable_statically"]


def test_the_report_names_ids_and_what_it_could_not_assess(tmp_path):
    report = assessment_markdown(_assess(tmp_path))
    assert "| Id | Module |" in report and "| M-01 |" in report
    assert "## Not assessable statically" in report
    assert "Environment-specific configuration" in report
    assert "Target Architecture" in report and "Design decides" not in report


def test_the_assessment_emits_a_valid_packet(tmp_path):
    out = assessment_packet(_assess(tmp_path), {"version": 1, "status": "draft"})
    assert out.ok, out.problems
    payload = out.packet.payload
    assert payload.commit == "a1b2c3d4"
    assert all(m.id.startswith("M-") for m in payload.modules)
    assert payload.not_assessable_statically


def test_an_unmeasured_factor_never_reads_plus_zero_in_the_report(tmp_path):
    report = assessment_markdown(_assess(tmp_path))
    risk = report[report.index("## Module risk"):report.index("## Not assessable")]
    assert "vulnerable_dependencies +0" not in risk
