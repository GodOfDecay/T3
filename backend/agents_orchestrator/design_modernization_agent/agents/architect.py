"""The Target Architecture agent's graph (Track 3 — Code Modernization, Phase E).

`app` is what both entry points run: the Orchestrator's dispatch (through
`orchestrator2/registry.py`) and the standalone socket (`design_modernization_agent_api.py`).
"""
from __future__ import annotations

from agents_orchestrator.design_modernization_agent.prompts.design_prompt import (
    DESIGN_MODERNIZATION_SYS_MESSAGE,
)
from agents_orchestrator.design_modernization_agent.tools.design_tools import TOOLS
from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.modernization_common.restore_tool import make_compare_tool, make_restore_tool
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools

AGENT_ID = "design_modernization"

#: The platform's document system bound to THIS stage (see discovery_agent/agents/assessor.py):
#: approved legacy documents to read, and this agent's own drafts to raise for approval.
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

#: Going back to an earlier design from the chat (research §12.4) — the page's Restore, too.
VERSION_TOOLS = [make_compare_tool(AGENT_ID, "target design"), make_restore_tool(AGENT_ID, "target design")]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *DOCUMENT_TOOLS, *VERSION_TOOLS],
                             checkpoint_name=AGENT_ID)

__all__ = ["AGENT_ID", "DESIGN_MODERNIZATION_SYS_MESSAGE", "DOCUMENT_TOOLS", "TOOLS", "VERSION_TOOLS", "app"]
