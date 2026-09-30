"""The Target Architecture agent as assembled: the tools its prompt names are bound, its prompt
carries the rules that are also enforced in code, and the socket turns away a Greenfield project.
"""
from __future__ import annotations

import re
import uuid as _uuid

import pytest
from sqlalchemy import text

from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser


def test_every_tool_the_prompt_names_is_bound():
    from agents_orchestrator.design_modernization_agent.agents import architect

    bound = {t.name for t in [*architect.TOOLS, *architect.DOCUMENT_TOOLS, *architect.VERSION_TOOLS]}
    named = set(re.findall(r"\b([a-z]+(?:_[a-z]+){1,4})\b", architect.DESIGN_MODERNIZATION_SYS_MESSAGE))
    tool_like = {n for n in named if n.split("_")[0] in {"read", "capture", "record", "export", "compare",
                                                          "restore", "list", "raise", "get", "search"}}
    assert tool_like, "the prompt should name its tools"
    assert tool_like <= bound, f"named but not bound: {sorted(tool_like - bound)}"
    assert {"record_target_design", "capture_legacy_interfaces", "read_assessment", "read_migration_brief",
            "export_target_design", "restore_version", "compare_versions", "read_legacy_file"} <= bound


def test_the_prompt_carries_the_rules_and_the_vocabulary():
    from agents_orchestrator.design_modernization_agent.agents.architect import DESIGN_MODERNIZATION_SYS_MESSAGE as p
    from agents_orchestrator.modernization_common.handover.packets import Pattern

    for pattern in Pattern.__args__:
        assert f"- {pattern}:" in p, pattern
    p = " ".join(p.split())
    assert "Hi — I'm the Target Architecture agent on the SDLC Platform." in p
    assert "never change a" in p and "ASK them; never assume" in p
    assert "brief_item" in p and "Mermaid" in p and "AS-IS, TRANSITION" in p
    assert "the Architect approves it, or a Project Admin as fallback" in p


def test_the_registry_entry_matches_the_research():
    from config.agent_registry import AGENT_REGISTRY, TRACK_PORTFOLIOS

    d = AGENT_REGISTRY["design_modernization"]
    assert (d.pipeline_position, d.output_artifact, d.gate_type) == (3, "target_design_artifacts", "approval_required")
    assert d.input_artifacts == ["migration_intent_payload", "discovery_artifacts"]
    assert TRACK_PORTFOLIOS["modernization"].index("design_modernization") == 2  # after the brief and the assessment


@pytest.mark.usefixtures("purge_created_orgs")
async def test_the_socket_refuses_a_greenfield_project_and_still_ends_the_turn(monkeypatch):
    from agents_orchestrator.design_modernization_agent import design_modernization_agent_api as api
    from tests.test_modernization_standalone import _FakeWebSocket

    org, bu, green = (str(_uuid.uuid4()) for _ in range(3))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseE')"),
                        {"i": org, "s": f"pe-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'G', 'greenfield')"), {"i": green, "w": bu, "t": org})
    await grant_role("u-arch", green, "architect", tenant_id=org, scope_kind="project")

    async def redeem(_ticket):
        return {"user_id": "u-arch", "tenant_id": org}

    monkeypatch.setattr(api, "_redeem_ws_ticket", redeem)
    socket = _FakeWebSocket(params={"ticket": "ok"}, inbound=[{
        "type": "user_message_with_files", "session_id": f"s-{_uuid.uuid4()}",
        "task_intent": "design the target", "pipeline_context": {"project_id": green}}])
    await api.design_modernization_ws(socket)
    refusal = next(e for e in socket.sent if e.get("type") == "agent_response")
    assert "not part of this project's delivery track" in refusal["message"]
    assert [e.get("type") for e in socket.sent][-2:] == ["stream_end", "activity_update"]
    from shared.db import engine
    await engine.dispose()
