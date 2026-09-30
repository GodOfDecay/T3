"""The cross-artifact rules `record_target_design` enforces (analysis/checks.py, D7, D14).

The ClaimTrack design fixture passes every rule against the ClaimTrack brief, the assessment and
a checkout holding the files it cites; then each rule is broken on its own, and must refuse with
a message that names the item. Pure functions — no database.
"""
from __future__ import annotations

from datetime import date

import pytest

from agents_orchestrator.design_modernization_agent.analysis import checks
from agents_orchestrator.design_modernization_agent.analysis.interfaces import (
    capture_interfaces,
    files_with_interfaces,
)
from agents_orchestrator.design_modernization_agent.tools.design_tools import _tree, check_design
from agents_orchestrator.modernization_common.handover.packets import DesignPayload
from tests.design_modernization.claimtrack import build_repo, design_payload, fixture

AS_OF = date(2026, 9, 29)
BRIEF = fixture("brief")["payload"]
ASSESSMENT = fixture("assessment")["payload"]


@pytest.fixture(scope="module")
def code(tmp_path_factory):
    root = build_repo(tmp_path_factory.mktemp("claimtrack"))
    files, dirs = _tree(root)
    inv = capture_interfaces(root, [{"id": m["id"], "path": m["path"]} for m in ASSESSMENT["modules"]])
    return files, dirs, files_with_interfaces(inv)


def _check(design: dict, code, brief=BRIEF, assessment=ASSESSMENT):
    files, dirs, captured = code
    return check_design(DesignPayload.model_validate(design), brief, assessment, 1, files, dirs, captured, AS_OF)


def _only(problems, *needles):
    assert len(problems) == 1, problems
    for n in needles:
        assert n in problems[0], problems[0]


def test_the_claimtrack_design_meets_every_rule(code):
    problems, notes = _check(design_payload(), code)
    assert problems == []
    assert not any("not checked" in n for n in notes)


# ── modules (D14) ────────────────────────────────────────────────────────────

def test_a_module_missing_from_the_design_is_refused(code):
    d = design_payload()
    d["modules"] = [m for m in d["modules"] if m["module_id"] != "M-04"]
    d["layers"] = [{**layer, "modules": [x for x in layer["modules"] if x != "M-04"]} for layer in d["layers"]]
    d["adrs"] = [{**a, "modules": [x for x in a["modules"] if x != "M-04"]} for a in d["adrs"]]
    _only(_check(d, code)[0], "M-04 claimtrack-agent-portal has no pattern", "`keep`")


def test_an_id_the_assessment_does_not_have_is_refused(code):
    d = design_payload()
    d["modules"][0]["module_id"] = "M-09"
    d["layers"] = [{**layer, "modules": [("M-09" if x == "M-01" else x) for x in layer["modules"]]} for layer in d["layers"]]
    d["adrs"] = [{**a, "modules": [("M-09" if x == "M-01" else x) for x in a["modules"]]} for a in d["adrs"]]
    problems = _check(d, code)[0]
    assert any("M-09 (claimtrack-core) is not a module of assessment v1 (commit a1b2c3d)" in p for p in problems)
    assert any("M-01 claimtrack-core has no pattern" in p for p in problems)


def test_ids_that_drifted_between_commits_are_refused(code):
    d = design_payload()
    d["modules"][2]["module"] = "claimtrack-reports"  # M-03 is claimtrack-batch in the pinned assessment
    _only(_check(d, code)[0], "M-03 is claimtrack-batch in assessment v1", "ids have shifted")


@pytest.mark.parametrize("field,value", [("tier", "manual"), ("risk_score", 10)])
def test_a_changed_tier_or_score_is_refused(code, field, value):
    d = design_payload()
    d["modules"][1][field] = value
    _only(_check(d, code)[0], "M-02 claimtrack-web: tier and score are the assessment's (llm_assisted, 56)")


# ── must not change ──────────────────────────────────────────────────────────

def test_every_must_not_change_item_needs_a_contract(code):
    d = design_payload()
    d["frozen_contracts"][1]["brief_item"] = None  # the bank file contract no longer claims the brief's words
    problems = _check(d, code)[0]
    assert any("“bank payment file format” must not change, and no contract freezes it" in p for p in problems)


def test_brief_words_are_compared_ignoring_case_and_spacing_only(code):
    d = design_payload()
    d["frozen_contracts"][1]["brief_item"] = "  Bank   Payment File Format "
    assert _check(d, code)[0] == []
    d["frozen_contracts"][1]["brief_item"] = "the bank file"
    problems = _check(d, code)[0]
    assert any("CT-02 says it freezes “the bank file”" in p for p in problems)


# ── contracts and traps in the code ──────────────────────────────────────────

def test_a_contract_location_that_is_not_in_the_code_is_refused(code):
    d = design_payload()
    d["frozen_contracts"][0]["legacy_location"] = "claimtrack-web/src/main/java/Nope.java:3"
    _only(_check(d, code)[0], "CT-01", "is not in the legacy code")


def test_a_location_with_a_line_number_or_an_elision_resolves(code):
    d = design_payload()
    d["frozen_contracts"][0]["legacy_location"] = "claimtrack-web/.../ClaimsApiController.java:5"
    assert _check(d, code)[0] == []


def test_confirmed_needs_the_inventory_or_the_brief(code):
    d = design_payload()
    d["frozen_contracts"].append({"id": "CT-05", "name": "core pom", "kind": "file",
                                  "legacy_location": "claimtrack-core/pom.xml", "consumers": [],
                                  "proof": "diff", "status": "confirmed"})
    _only(_check(d, code)[0], "CT-05 core pom is confirmed", "mark it proposed")
    d["frozen_contracts"][-1]["status"] = "proposed"
    assert _check(d, code)[0] == []


def test_without_code_confirmed_needs_the_brief_and_it_is_said(code):
    d = design_payload()
    problems, notes = check_design(DesignPayload.model_validate(d), BRIEF, ASSESSMENT, 1, None, None, None, AS_OF)
    _only(problems, "CT-04", "there is no legacy code to show it")
    assert any("not checked against the code" in n for n in notes)


def test_a_trap_must_name_a_place_in_the_code(code):
    d = design_payload()
    d["traps"][4]["where"] = "queries across web, batch, reports"
    _only(_check(d, code)[0], "TR-05 does not say where in the code it bites")
    d["traps"][4]["where"] = "claimtrack-reports/sql/*.java"
    _only(_check(d, code)[0], "TR-05", "names nothing in the legacy code")


def test_a_folder_names_the_files_in_it_and_parent_paths_name_nothing(code):
    files, dirs, _captured = code
    assert checks.resolve("claimtrack-batch/src/main/resources/", files, dirs) == {
        "claimtrack-batch/src/main/resources/application.properties"}
    assert checks.resolve("../claimtrack-core/pom.xml", files, dirs) == set()
    assert checks.resolve("claimtrack-web/../claimtrack-core/pom.xml", files, dirs) == set()


# ── versions ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("target,needle", [
    ("Java 21 · Node 18 · Python 3.12", "Node.js 18 is past its end of support"),
    ("Java 21 · Node 22 · Python 3.12", "Node.js 22 ends support on 2027-04-30, within a year"),
    ("Java 7 · Node 24", "Java 7 is past its end of support"),
    ("Python 3.9 · Java 21", "Python 3.9 is past"),
    (".NET 6 on App Service", ".NET 6 is past"),
    ("Java latest", "never “latest”"),
])
def test_a_target_past_or_near_end_of_life_is_refused(code, target, needle):
    d = design_payload()
    d["layers"][1]["target"] = target
    _only(_check(d, code)[0], "Runtime target", needle)


def test_a_legacy_version_is_noted_not_refused(code):
    d = design_payload()
    d["layers"][1]["target"] = "Java 11 · Node 24"
    problems, notes = _check(d, code)
    assert problems == [] and any("Java 11 is supported but frozen" in n for n in notes)


def test_dotnet_framework_is_not_read_as_modern_dotnet():
    assert checks.runtimes_in(".NET Framework 4.8 and .NET 8") == [
        checks.Runtime(".NET Framework", "4.8"), checks.Runtime(".NET", "8")]


# ── data, diagrams, questions ────────────────────────────────────────────────

def test_a_changing_database_needs_the_data_migration(code):
    d = design_payload()
    d["data_migration"] = None
    _only(_check(d, code)[0], "The Database layer changes", "no data-migration plan")
    d["layers"][3]["today"] = d["layers"][3]["target"]  # the database stays as it is
    assert _check(d, code)[0] == []


@pytest.mark.parametrize("drop,needle", [(0, "no AS-IS diagram"), (1, "no TRANSITION diagram"), (2, "no TO-BE diagram")])
def test_the_three_diagrams_are_required(code, drop, needle):
    d = design_payload()
    del d["diagrams"][drop]
    _only(_check(d, code)[0], needle)


def test_a_diagram_that_is_not_mermaid_is_refused(code):
    d = design_payload()
    d["diagrams"][0]["mermaid"] = "Brokers -> Web -> DB"
    _only(_check(d, code)[0], "“AS-IS container” diagram is not Mermaid")
    d["diagrams"][0]["mermaid"] = "---\ntitle: x\n---\n%% note\nC4Container\n  Person(b, \"Broker\")"
    assert _check(d, code)[0] == []


def test_an_unanswered_question_from_the_assessment_is_refused_and_open_is_allowed(code):
    d = design_payload()
    q = d["resolved_questions"].pop(1)["question"]
    _only(_check(d, code)[0], f"“{q}”", "Never assume it")
    d["open_questions"] = [q]
    assert _check(d, code)[0] == []
