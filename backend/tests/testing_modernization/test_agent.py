"""Equivalence Testing — the agent as assembled (Phase G): graph and tools, prompt rules, registry,
Orchestrator routing, the plan formatter, the baseline document. No database, no Docker."""
from __future__ import annotations

import pytest

from agents_orchestrator.orchestrator2 import router
from agents_orchestrator.orchestrator2.registry import agent_ids_for_track
from tests.testing_modernization import lite


def test_the_graph_has_the_baseline_tools_and_the_legacy_code_read_only():
    from agents_orchestrator.testing_modernization_agent.agents import tester

    names = {t.name for t in [*tester.TOOLS, *tester.LEGACY_TOOLS]}
    assert {"read_migration_plan", "get_ledger", "get_capture_profile", "save_capture_profile", "plan_capture",
            "capture_baseline", "record_baseline", "export_baseline_document"} <= names
    assert {"read_legacy_file", "search_legacy_code", "pull_legacy_code"} <= names
    assert not any("write" in n or "push" in n for n in names - {"save_capture_profile"})
    assert tester.AGENT_ID == "testing_modernization"


def test_the_prompt_says_propose_never_apply_consent_and_masked_only():
    from agents_orchestrator.testing_modernization_agent.agents.tester import EQUIVALENCE_SYS_MESSAGE as p

    assert "Hi — I'm the Equivalence Testing agent on the SDLC" in p
    assert "PROPOSE a rule to Migration Strategy" in p and "never apply one" in p
    assert "only after an explicit yes on the" in p and "Only QA or a Project Admin of this project" in p
    assert "Data is\n   synthetic or sample only" in p or "synthetic or sample only" in p
    assert "never copy a recording into the chat" in p
    # Phase J: Verify mode is built; its prompt says the tools classify and an accepted change needs an ADR.
    assert "VERIFY MODE" in p and "not available yet" not in p
    assert "ONLY when an ADR on this module explicitly allows" in p
    assert "a performance criterion not measured is \"not run\"" in p


def test_registry_portfolio_and_upstream_reads():
    from agents_orchestrator.modernization_common.legacy_code import TRACK3_STAGES
    from agents_orchestrator.modernization_common.standalone import _UPSTREAM_STAGE
    from config.agent_registry import AGENT_REGISTRY

    d = AGENT_REGISTRY["testing_modernization"]
    assert (d.pipeline_position, d.output_artifact, d.gate_type) == (5, "equivalence_artifacts", "approval_required")
    assert d.input_artifacts == ["strategy_artifacts", "target_design_artifacts"]
    assert agent_ids_for_track("modernization")[4] == "testing_modernization"
    assert _UPSTREAM_STAGE["strategy_artifacts"] == ("strategy", "Migration plan")
    assert "testing_modernization" in TRACK3_STAGES


@pytest.mark.parametrize("text", ["run the equivalence testing agent", "open the equivalence testing agent",
                                  "use the baseline agent", "run the testing agent"])
async def test_naming_it_routes_to_it_without_a_model_call(monkeypatch, text):
    async def must_not_call(*_a, **_kw):
        raise AssertionError("an explicit command must not cost a model call")

    monkeypatch.setattr(router, "_ask_model", must_not_call)
    decision = await router.route(text, history=[], run_id="r", tenant_id="t", project_id="p",
                                  model_id=None, offering_id=None, track="modernization")
    assert decision.agent_id == "testing_modernization"


def test_on_greenfield_testing_is_track_1s_testing_agent():
    assert router.prefilter("run the equivalence testing agent", agent_ids_for_track("greenfield")) is None
    assert router.prefilter("run the testing agent", agent_ids_for_track("greenfield")) == "testing"


def test_the_orchestrator_prompt_separates_planning_baselines_from_capturing_them():
    from agents_orchestrator.orchestrator2.registry import registry_for_track

    prompt = router._system_prompt(registry_for_track("modernization"), "modernization")
    assert "RECORDING WHAT THE LEGACY SYSTEM DOES is Equivalence Testing work" in prompt
    assert "Deciding\n  WHICH baselines are needed is planning (Migration Strategy)" in prompt


def test_the_plan_is_pre_loaded_compactly_with_its_normalization():
    from config.context_broker import _ARTIFACT_FIELDS, _ARTIFACT_FORMATTERS

    assert "strategy_artifacts" in _ARTIFACT_FIELDS
    out = _ARTIFACT_FORMATTERS["strategy_artifacts"](lite.stored_plan())
    assert "EC-03 (M-02): BANKPAY file bytes — byte_identical; normalized: BANKPAY_*.txt#L1" in out
    assert "WAVES: W0 (foundation); W1 M-01; W2 M-02" in out


def test_the_baseline_document_shows_hashes_counts_and_proposals_never_data():
    from agents_orchestrator.testing_modernization_agent.baseline_document import baseline_markdown, headline
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import build_artifact
    from tests.testing_modernization.test_units import NOISE

    manifest = {"id": "cap-20260930000000-aaaaaa", "mapping": lite.MAPPING, "noise": NOISE,
                "notCaptured": lite.NOT_CAPTURED, "stubs": ["fraudscore"], "finishedAt": "2026-09-30T08:00:00+00:00",
                "scenarios": [{"id": s, "kind": NOISE[s]["kind"], "cases": NOISE[s]["cases"], "describes": s} for s in NOISE]}
    art = build_artifact(lite.plan(), manifest, lite.PROPOSALS, hash_of=lambda scs: "f" * 64, region="local-dev",
                         sources={"plan": {"version": 2, "status": "published"}}, system_name="ClaimTrack Lite",
                         notes=["n"], recorded_at=None)
    md = baseline_markdown(art)
    assert headline(art) == ("3 baselines, 3 criteria recorded, modules M-01, M-02, 2 rule proposals to Migration "
                             "Strategy, 1 not captured")
    assert "Built from migration plan v2 (approved)." in md
    assert "| BL-03 | M-02 | EC-03 | 1 runs | `ffffffffffffffff…` | local-dev | BANKPAY_20270131.txt#L1 |" in md
    assert "| EC-01 | requestId | ignore the value, require it present |" in md
    assert "- EC-04: a load test — measured in Verify mode" in md
    assert art["placements"][0] == {"module_id": "M-01", "baseline_ids": ["BL-01", "BL-02"]}
    assert art["scenarios"][0]["varying"] == {"generatedAt": 4, "requestId": 5}
