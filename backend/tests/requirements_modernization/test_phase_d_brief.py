"""Phase D — Migration Intent (research §6.1): `must_not_change` word for word, `kind` on every
success measure, the hand-over packet checked at record time, the prompt's hand-over and
going-back rules, and the restore/compare tools. Pure: no database (the transcript is faked).
"""
from __future__ import annotations

import pytest

from agents_orchestrator.modernization_common import verbatim
from agents_orchestrator.requirements_modernization_agent.brief import brief_markdown
from agents_orchestrator.requirements_modernization_agent.brief_document import render_brief
from agents_orchestrator.requirements_modernization_agent.tools import brief_tools
from config.ws_helper import set_session_id, set_tenant_id, set_user_id
from shared.models.artifacts import MigrationIntentArtifact

SAID = ["ClaimTrack must keep the /api/v1 claims API brokers call, and the BACS Standard 18 payment file."]

BRIEF = {
    "system_name": "ClaimTrack",
    "goal": "Move ClaimTrack onto supported runtimes by June 2027.",
    "business_drivers": ["Java 7 is out of support"],
    "current_stack": "Java 7 on WebLogic",
    "target_stack": "Java 21 on Azure Container Apps",
    "in_scope": ["claims intake"],
    "constraints": ["Off the old servers by 30 June 2027"],
    "must_not_change": ["the /api/v1 claims API brokers call", "the BACS Standard 18 payment file"],
    "success_measures": [{"metric": "Payouts identical", "target": "100% on replay", "kind": "equivalence"}],
    "success_criteria": ["Identical payouts on recorded claims"],
}


@pytest.fixture(autouse=True)
def _ctx(tmp_path, monkeypatch):
    set_session_id(f"pd-{tmp_path.name}")
    set_user_id("")
    set_tenant_id("t-1")
    stored: list = []

    async def fake_persist(brief):
        stored.append(brief)
        return "Saved."

    async def said(_session, _tenant):
        return list(SAID)

    monkeypatch.setattr(brief_tools, "_persist", fake_persist)
    monkeypatch.setattr(verbatim, "user_texts", said)
    yield stored
    brief_tools._LAST_BRIEF.clear()
    set_tenant_id(None)


async def test_the_users_words_are_recorded(_ctx):
    out = await brief_tools.record_migration_intent.ainvoke(BRIEF)
    assert not out.startswith("NOT RECORDED"), out
    assert _ctx[0].must_not_change == BRIEF["must_not_change"]
    assert _ctx[0].success_measures[0].kind == "equivalence"


async def test_a_paraphrase_is_refused_and_named(_ctx):
    out = await brief_tools.record_migration_intent.ainvoke(
        {**BRIEF, "must_not_change": ["the claims API", "the BACS Standard 18 payment file"]})
    assert out.startswith("NOT RECORDED YET") and '"the claims API"' in out and "BACS" not in out.split(":")[1]
    assert _ctx == []


async def test_an_unreadable_conversation_is_not_a_refusal(_ctx, monkeypatch):
    async def unreadable(_s, _t):
        return None

    monkeypatch.setattr(verbatim, "user_texts", unreadable)
    out = await brief_tools.record_migration_intent.ainvoke({**BRIEF, "must_not_change": ["anything at all"]})
    assert not out.startswith("NOT RECORDED"), out


async def test_a_measure_without_a_kind_cannot_be_handed_over(_ctx):
    out = await brief_tools.record_migration_intent.ainvoke(
        {**BRIEF, "success_measures": [{"metric": "Payouts identical", "target": "100%"}]})
    assert out.startswith("NOT RECORDED YET") and "cannot be handed to the next agents" in out
    assert "Success measure 1 has no kind (equivalence, performance, security, schedule or cost)." in out
    assert ".." not in out
    assert _ctx == []


async def test_a_brief_with_no_measure_at_all_cannot_be_handed_over(_ctx):
    out = await brief_tools.record_migration_intent.ainvoke({**BRIEF, "success_measures": []})
    assert out.startswith("NOT RECORDED YET") and "There is no measurable success measure." in out


def test_kind_is_normalised_and_unknown_kinds_are_none():
    b = MigrationIntentArtifact(success_measures=[{"metric": "a", "kind": " Performance "},
                                                  {"metric": "b", "kind": "vibes"}])
    assert [m.kind for m in b.success_measures] == ["performance", None]


def test_the_document_shows_both(tmp_path):
    brief = MigrationIntentArtifact(**{**{k: v for k, v in BRIEF.items() if k not in (
        "business_drivers", "current_stack", "target_stack")}, "business_drivers": ["x"]})
    md = brief_markdown(brief)
    assert "Must not change" in md and "“the /api/v1 claims API brokers call”" in md
    assert "| Measure | Kind | Today | Target |" in md and "| Equivalence |" in md
    render_brief(brief, str(tmp_path / "b.docx"), {"version": 1, "status": "draft"})
    render_brief(brief, str(tmp_path / "b.pdf"), {"version": 1, "status": "draft"})
    import docx  # noqa: PLC0415

    text = "\n".join(p.text for p in docx.Document(str(tmp_path / "b.docx")).paragraphs)
    assert "the /api/v1 claims API brokers call" in text and "Must not change" in text


def test_the_prompts_carry_the_hand_over_and_going_back_rules():
    from agents_orchestrator.discovery_agent.prompts.discovery_prompt import DISCOVERY_SYS_MESSAGE
    from agents_orchestrator.requirements_modernization_agent.prompts.migration_intent_prompt import (
        MIGRATION_INTENT_SYS_MESSAGE,
    )

    for heading in ("MUST NOT CHANGE", "WORD FOR WORD", "AFTER THE BRIEF", "GOING BACK"):
        assert heading in MIGRATION_INTENT_SYS_MESSAGE, heading
    assert "kind: equivalence, performance, security, schedule or cost" in MIGRATION_INTENT_SYS_MESSAGE
    assert "GOING BACK" in DISCOVERY_SYS_MESSAGE and "Not assessable" in DISCOVERY_SYS_MESSAGE
    assert "Target Architecture designs the target" in DISCOVERY_SYS_MESSAGE


def test_both_agents_bind_compare_and_restore():
    from agents_orchestrator.discovery_agent.agents.assessor import VERSION_TOOLS as D
    from agents_orchestrator.requirements_modernization_agent.agents.intake import VERSION_TOOLS as R

    assert [t.name for t in D] == [t.name for t in R] == ["compare_versions", "restore_version"]


async def test_unchecked_wording_is_not_called_the_users_own_words(_ctx, monkeypatch):
    """Review finding 2: when the conversation cannot be read the brief must not claim the
    wording was checked — the flag is recorded and the caption and reply say so."""
    async def unreadable(_s, _t):
        return None

    monkeypatch.setattr(verbatim, "user_texts", unreadable)
    out = await brief_tools.record_migration_intent.ainvoke(BRIEF)
    brief = _ctx[0]
    assert brief.must_not_change_verified is False
    assert "could not be checked against this conversation" in out
    md = brief_markdown(brief)
    assert "Not checked against the conversation" in md and "In the user's own words" not in md


async def test_checked_wording_is_flagged(_ctx):
    await brief_tools.record_migration_intent.ainvoke(BRIEF)
    assert _ctx[0].must_not_change_verified is True
    assert "In the user's own words" in brief_markdown(_ctx[0])


async def test_a_refusal_says_how_to_bring_wording_from_a_document(_ctx):
    out = await brief_tools.record_migration_intent.ainvoke({**BRIEF, "must_not_change": ["the claims gateway"]})
    assert "paste those lines into the chat" in out

