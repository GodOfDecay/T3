"""Phase B retrofit: Migration Intent follows the project's approved tech stack, and every
Track 3 prompt names only tools its agent actually binds.

The tech stack is read by code (Agent Studio's effective stack: project selection → BU
default → none) and stamped on the recorded brief; the model supplies only the departures.
No database: the stack resolver is replaced at its seam, `current_project_tech_stack`.
"""
from __future__ import annotations

import pytest

from agents_orchestrator.modernization_common import tech_stack as ts
from agents_orchestrator.requirements_modernization_agent.brief import _stack_line
from shared.services.tech_stack import EffectiveTechStack, TechStack

pytestmark = pytest.mark.unit

STACK = TechStack(id="s1", scope="workspace", workspace_id="w1", project_id=None, name="Azure Java Standard",
                  categories={"backend": ["Java", "Spring Boot"], "database": ["Azure MySQL"]}, is_default=True)


def _resolver(monkeypatch, result):
    from shared.services import tech_stack_store

    async def current():
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(tech_stack_store, "current_project_tech_stack", current)


async def test_the_business_unit_default_is_read_with_its_source(monkeypatch):
    _resolver(monkeypatch, EffectiveTechStack(STACK, "bu_default"))
    stack = await ts.effective_stack()
    assert (stack["name"], stack["source"], stack["source_text"]) == (
        "Azure Java Standard", "bu_default", "the Business Unit default")
    text = ts.describe(stack)
    assert '"Azure Java Standard" (the Business Unit default)' in text
    assert "backend: Java, Spring Boot" in text and "DEPARTURE" in text


async def test_no_stack_says_recommend_freely(monkeypatch):
    _resolver(monkeypatch, EffectiveTechStack(None, "none"))
    text = ts.describe(await ts.effective_stack())
    assert "no approved tech stack" in text and "recommend the target freely" in text


async def test_a_stale_selection_warning_is_passed_on(monkeypatch):
    warning = "The tech stack chosen for this project was deleted. Following the Business Unit default instead."
    _resolver(monkeypatch, EffectiveTechStack(STACK, "bu_default", warning))
    assert f"Tell the user: {warning}" in ts.describe(await ts.effective_stack())


async def test_an_unreadable_stack_is_said_not_treated_as_none(monkeypatch):
    _resolver(monkeypatch, RuntimeError("db down"))
    stack = await ts.effective_stack()
    assert stack["source"] == "unreadable"
    assert "could not be read" in stack["warning"]
    assert "do not treat it as 'no stack applies'" in ts.describe(stack)
    # …and the brief records it as unknown, not as "none" (Phase B review, finding 6).
    line = _stack_line(ts.applied_stack(stack, []))
    assert "could not be read" in line and "none" not in line


async def test_the_recorded_brief_carries_the_stack_set_by_code(monkeypatch):
    """The stack comes from the resolver even when the model says nothing about it; only
    the departures come from the model."""
    from agents_orchestrator.requirements_modernization_agent.tools import brief_tools
    from agents_orchestrator.modernization_common import versions

    _resolver(monkeypatch, EffectiveTechStack(STACK, "project_selection"))

    async def not_saved(brief):
        return "Not saved: test."

    async def no_version(stage, payload):
        return None

    monkeypatch.setattr(brief_tools, "_persist", not_saved)
    monkeypatch.setattr(versions, "freeze_version", no_version)
    brief_tools._LAST_BRIEF.clear()
    reply = await brief_tools.record_migration_intent.ainvoke({
        "system_name": "ClaimTrack", "goal": "Leave Dallas on supported runtimes.",
        "business_drivers": ["End of support"],
        "success_measures": [{"metric": "Payouts identical", "target": "100%", "kind": "equivalence"}],
        "current_stack": "Java 7", "target_stack": "Java 21", "in_scope": ["all five components"],
        "constraints": ["off Dallas by 30 Jun 2027"], "success_criteria": ["payouts identical"],
        "recommendation_summary": "Java 21 and React.",
        "stack_departures": ["React 18 for the broker portal: the stack names no front end"],
    })
    (brief,) = brief_tools._LAST_BRIEF.values()
    assert brief.tech_stack == {
        "name": "Azure Java Standard", "source": "project_selection", "warning": None,
        "departures": ["React 18 for the broker portal: the stack names no front end"],
    }
    assert "**Approved tech stack:** Azure Java Standard (chosen for this project). Departures:" in reply


@pytest.mark.parametrize("stack,expected", [
    (None, "not recorded (this brief pre-dates the check)"),
    ({"name": None, "source": "none"}, "none — the target was recommended freely"),
    ({"name": "S", "source": "bu_default", "departures": []}, "S (the Business Unit default). The recommendation stays within it."),
])
def test_the_brief_states_the_stack(stack, expected):
    assert expected in _stack_line(stack)


@pytest.mark.parametrize("module,prompt_attr", [
    ("agents_orchestrator.requirements_modernization_agent.agents.intake", "MIGRATION_INTENT_SYS_MESSAGE"),
    ("agents_orchestrator.discovery_agent.agents.assessor", "DISCOVERY_SYS_MESSAGE"),
    ("agents_orchestrator.design_modernization_agent.agents.architect", "DESIGN_MODERNIZATION_SYS_MESSAGE"),
    ("agents_orchestrator.strategy_agent.agents.planner", "STRATEGY_SYS_MESSAGE"),
])
def test_every_tool_a_prompt_names_is_bound(module, prompt_attr):
    """A prompt naming an unbound tool sends the model after a call that fails."""
    import importlib

    agent = importlib.import_module(module)
    prompt = getattr(agent, prompt_attr)
    bound = {t.name for t in [*agent.TOOLS, *agent.DOCUMENT_TOOLS]}
    for name in ("list_project_documents", "read_document", "raise_document_for_approval",
                 "get_project_tech_stack"):
        if name in prompt:
            assert name in bound, f"{prompt_attr} names {name} but the agent does not bind it"
    assert {"list_project_documents", "read_document", "raise_document_for_approval"} <= bound


@pytest.mark.parametrize("module", [
    "agents_orchestrator.requirements_modernization_agent.agents.intake",
    "agents_orchestrator.discovery_agent.agents.assessor",
    "agents_orchestrator.design_modernization_agent.agents.architect",
    "agents_orchestrator.strategy_agent.agents.planner",
])
def test_the_graph_is_built_with_the_document_tools(module, monkeypatch):
    """What reaches `build_tool_agent_graph` — not a list beside it — is what the model can call."""
    import importlib

    from agents_orchestrator.modernization_common import graph

    seen: dict = {}

    def capture(*, agent_type, tools, checkpoint_name, **_kw):
        seen[agent_type] = {t.name for t in tools}
        return object()

    monkeypatch.setattr(graph, "build_tool_agent_graph", capture)
    agent = importlib.import_module(module)
    try:
        importlib.reload(agent)
        assert {"list_project_documents", "read_document", "raise_document_for_approval"} <= seen[agent.AGENT_ID]
    finally:
        monkeypatch.undo()
        importlib.reload(agent)  # put the real compiled graph back for later tests
