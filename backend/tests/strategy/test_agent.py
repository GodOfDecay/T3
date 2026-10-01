"""The Migration Strategy agent as assembled: the tools its prompt names are bound, the prompt carries
the rules that are also enforced in code, it is wired to the Orchestrator and files its plan as a
deliverable, and the context it is handed names what its criteria must protect."""
from __future__ import annotations

import re

import pytest

from agents_orchestrator.orchestrator2 import router
from agents_orchestrator.orchestrator2.registry import agent_ids_for_track


def test_every_tool_the_prompt_names_is_bound():
    from agents_orchestrator.strategy_agent.agents import planner

    bound = {t.name for t in [*planner.TOOLS, *planner.DOCUMENT_TOOLS, *planner.VERSION_TOOLS]}
    named = set(re.findall(r"\b([a-z]+(?:_[a-z]+){1,4})\b", planner.STRATEGY_SYS_MESSAGE))
    tool_like = {n for n in named if n.split("_")[0] in {"read", "propose", "check", "estimate", "record", "export",
                                                          "preview", "create", "compare", "restore", "list", "raise"}}
    assert tool_like <= bound, f"named but not bound: {sorted(tool_like - bound)}"
    assert {"propose_wave_order", "check_calendar", "estimate_effort", "record_migration_strategy",
            "preview_wave_work_items", "create_wave_work_items"} <= tool_like


def test_the_prompt_carries_the_rules():
    from agents_orchestrator.strategy_agent.agents.planner import STRATEGY_SYS_MESSAGE as p

    p = " ".join(p.split())
    assert "Hi — I'm the Migration Strategy agent on the SDLC Platform." in p
    assert "Wave 0 is always the foundation" in p and "order exception citing that ADR" in p
    assert "Never move a date the user gave" in p and "never from a template" in p
    assert "only call create_wave_work_items after an explicit yes" in p


def test_registry_and_portfolio():
    from config.agent_registry import AGENT_REGISTRY

    d = AGENT_REGISTRY["strategy"]
    assert d.input_artifacts == ["migration_intent_payload", "discovery_artifacts", "target_design_artifacts"]
    assert (d.pipeline_position, d.output_artifact) == (4, "strategy_artifacts")
    assert agent_ids_for_track("modernization").index("strategy") == 3  # after the brief, assessment and design


@pytest.mark.parametrize("text", ["run the migration strategy agent", "open the strategy agent",
                                  "use the wave plan agent"])
async def test_naming_it_routes_to_it_without_a_model_call(monkeypatch, text):
    async def must_not_call(*_a, **_kw):
        raise AssertionError("an explicit command must not cost a model call")

    monkeypatch.setattr(router, "_ask_model", must_not_call)
    decision = await router.route(text, history=[], run_id="r", tenant_id="t", project_id="p",
                                  model_id=None, offering_id=None, track="modernization")
    assert decision.agent_id == "strategy"


def test_it_is_never_offered_on_greenfield():
    assert router.prefilter("run the strategy agent", agent_ids_for_track("greenfield")) is None
    assert "PLANNING THE MOVE is Migration Strategy work" in router._system_prompt(
        {a: None for a in agent_ids_for_track("modernization")}, "modernization")


def test_the_plan_is_filed_as_a_deliverable():
    from agents_orchestrator.orchestrator2.deliverables import render
    from agents_orchestrator.strategy_agent.strategy_document import strategy_markdown
    from tests.strategy.scenarios import payroll

    rows = render("strategy", strategy_markdown({**payroll()[3], "system_name": "Payroll"}))
    assert len(rows) == 1 and rows[0]["title"] == "Migration Strategy — Payroll"


def test_the_design_context_names_what_criteria_must_protect():
    from config.context_broker import _ARTIFACT_FORMATTERS
    from tests.strategy.scenarios import payroll

    text = _ARTIFACT_FORMATTERS["target_design_artifacts"](payroll()[2])
    assert "M-05 Payroll.Archive: keep" in text
    assert "FROZEN CONTRACTS (each needs a criterion): CT-01 BACS payment file" in text
    assert "ADRS: ADR-01" in text


def test_a_large_design_says_how_many_modules_the_context_leaves_out():
    from config.context_broker import _fmt_target_design

    design = {"modules": [{"module_id": f"M-{i:03d}", "module": f"m{i}", "patterns": ["rewrite"]} for i in range(200)]}
    out = _fmt_target_design(design)
    assert "M-059 m59" in out and "M-060" not in out
    assert "… and 140 more modules — read_target_design lists them all" in out


async def test_a_database_error_is_said_never_taken_as_nothing_recorded(monkeypatch):
    import shared.db
    from agents_orchestrator.modernization_common import inputs
    from config.ws_helper import set_project_id, set_tenant_id

    def down(*_a, **_k):
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(shared.db, "get_db_session_for_tenant", down)
    set_tenant_id("tenant")
    set_project_id("project")
    try:
        got = await inputs.read_inputs(["requirements_modernization", "design_modernization"])
    finally:
        set_tenant_id(None)
        set_project_id(None)
    assert all(i.problems == ["It could not be read just now (a database error). Try again."] for i in got.values())
    assert "could not be read just now" in inputs.missing_line(got["design_modernization"])
