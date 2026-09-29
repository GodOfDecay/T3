"""Agents 1 and 2 emit their hand-over packets (`handover/emit.py`, Phase D). Pure: no database.

Guarding: the brief's `must_not_change` reaches the packet word for word; a success measure with
no `kind` is refused, saying so; a prose deadline is kept in the user's words, never dropped or
turned into a date; the assessment's graph and flags are by M-xx id; not-assessable questions and
the golden-master pointer are carried; a grant read is pinned as the draft it was; an assessment
with no commit is refused.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from agents_orchestrator.modernization_common.handover.emit import (
    assessment_packet, brief_packet, envelope_of,
)

ENVELOPE = {"version": 3, "status": "draft", "built_from": [], "produced_by": {"user_id": "u-ba"}}

BRIEF = {
    "system_name": "ClaimTrack", "goal": "Leave the Dallas data centre by Q3 2027.",
    "target_state": {"stack": "Java 21 on Azure Container Apps"},
    "in_scope": ["claims intake", "adjudication"], "out_of_scope": ["reporting"],
    "constraints": ["No downtime in claims week"], "deadline": "2027-09-30", "budget": "£1.2m",
    "must_not_change": ["the /api/v1 claims API used by brokers", "Bank payment file format (BACS Standard 18)"],
    "success_measures": [
        {"metric": "claim payouts identical", "current": "", "target": "100% on replay", "kind": "equivalence"},
        {"metric": "p95 claim lookup", "current": "2.1s", "target": "< 800ms", "kind": "performance"},
    ],
    "stakeholders": [{"name": "Dana Reyes", "role": "Business owner, Claims"}, {"name": "Sam", "role": "Architect"}],
    "open_questions": ["Is the CR-4 return still filed quarterly?"],
}


def test_a_complete_brief_emits_its_packet_with_the_users_words():
    out = brief_packet(BRIEF, ENVELOPE)
    assert out.ok, out.problems
    p = out.packet.payload
    assert p.must_not_change == BRIEF["must_not_change"]
    assert [m.kind for m in p.success_measures] == ["equivalence", "performance"]
    assert (p.target_stack, p.business_owner, str(p.deadline)) == (["Java 21 on Azure Container Apps"],
                                                                  "Dana Reyes", "2027-09-30")
    assert out.as_dict()["packet"]["payload"]["scope"] == {"in": ["claims intake", "adjudication"], "out": ["reporting"]}


def test_a_measure_without_a_kind_is_refused_and_says_so():
    brief = {**BRIEF, "success_measures": [{"metric": "payouts identical", "target": "100%"}]}
    out = brief_packet(brief, ENVELOPE)
    assert not out.ok and out.problems == [
        "Success measure 1 has no kind (equivalence, performance, security, schedule or cost)."]


def test_a_prose_deadline_is_kept_in_the_users_words():
    out = brief_packet({**BRIEF, "deadline": "end of Q3 2027"}, ENVELOPE)
    assert out.ok, out.problems
    assert out.packet.payload.deadline is None
    assert "Deadline: end of Q3 2027" in out.packet.payload.constraints


def test_an_empty_must_not_change_entry_is_refused():
    out = brief_packet({**BRIEF, "must_not_change": ["the API", "  "]}, ENVELOPE)
    assert not out.ok and any("must_not_change" in p for p in out.problems)


def test_the_envelope_pins_a_grant_read_as_the_draft_it_was():
    row = SimpleNamespace(version=2, status="draft", produced_by="u-ba", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                          built_from=[{"stage": "requirements_modernization", "version": 1, "status": "granted"},
                                      {"artifact": "migration_intent_payload", "stage": "x", "version": 1,
                                       "status": "published"}][:1])
    env = envelope_of(row)
    assert env["built_from"] == [{"artifact": "migration_intent_payload", "version": 1, "status": "draft"}]
    assert env["produced_at"].startswith("2026-09-01")


ASSESSMENT = {
    "repository": {"url": "https://dev.azure.com/claimtrack/legacy", "commit": "a1b2c3d"},
    "modules": [
        {"id": "M-02", "name": "claims-batch", "path": "batch", "loc": 900, "dependents": [], "depends_on": ["claims-core"],
         "blockers": [], "runtime": {"name": "Java", "version": "7", "status": "eol", "eol_date": "2022-07-19"},
         "risk": {"score": 62, "tier": "llm_assisted"}},
        {"id": "M-01", "name": "claims-core", "path": "api", "loc": 4000, "dependents": ["claims-batch"], "depends_on": [],
         "blockers": [], "runtime": {"name": "", "version": "", "status": "unknown"}, "risk": {"score": 30, "tier": "mechanical"}},
    ],
    "flags": {"eol": [{"module": "claims-batch"}], "deprecated": [], "vulnerable": []},
    "golden_master": {"status": "not_captured", "baselines": []},
    "not_assessable_statically": [{"topic": "runtime", "modules": ["M-02"], "question": "Which Java does M-02 run on?"}],
}


def test_the_assessment_packet_is_by_module_id():
    out = assessment_packet(ASSESSMENT, {**ENVELOPE, "version": 1})
    assert out.ok, out.problems
    p = out.packet.payload
    assert [m.id for m in p.modules] == ["M-01", "M-02"]
    assert p.graph == [("M-02", "M-01")]
    assert p.flags.eol == ["M-02"]
    assert p.modules[0].runtime is None and p.modules[1].runtime.status == "eol"
    assert p.modules[0].fan_in == 1
    assert p.not_assessable_statically == ["Which Java does M-02 run on?"]
    assert p.golden_master.status == "not_captured"


def test_an_assessment_without_a_commit_is_refused():
    out = assessment_packet({**ASSESSMENT, "repository": {"url": "x"}}, {**ENVELOPE, "version": 1})
    assert not out.ok and out.problems == ["The assessed commit is not recorded."]


def test_a_captured_golden_master_carries_its_baselines():
    out = assessment_packet({**ASSESSMENT, "golden_master": {"status": "captured", "baselines": ["BL-01"]}},
                            {**ENVELOPE, "version": 1})
    assert out.ok and out.packet.payload.golden_master.baselines == ["BL-01"]


def test_a_schema1_assessment_gets_one_sentence_with_the_remedy():
    """Review finding 4c: not one validation error per module and per edge."""
    old = {**ASSESSMENT, "modules": [{k: v for k, v in m.items() if k != "id"} for m in ASSESSMENT["modules"]]}
    out = assessment_packet(old, {**ENVELOPE, "version": 1})
    assert out.problems == ["This assessment was made before modules had ids (M-01, …). Run the assessment "
                            "again to hand it to Target Architecture."]


def test_modules_are_handed_over_in_numeric_order():
    rows = [{**ASSESSMENT["modules"][1], "id": f"M-{n:02d}", "name": f"m{n}", "path": f"p{n}", "depends_on": []}
            for n in (11, 9, 100)]  # as strings, "M-100" sorts before "M-11"
    out = assessment_packet({**ASSESSMENT, "modules": rows, "flags": {}}, {**ENVELOPE, "version": 1})
    assert out.ok, out.problems
    assert [m.id for m in out.packet.payload.modules] == ["M-09", "M-11", "M-100"]
