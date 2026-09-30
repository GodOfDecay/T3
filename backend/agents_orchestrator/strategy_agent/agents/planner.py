"""The Migration Strategy agent's graph (Track 3 — Code Modernization, Phase F).

`app` is what both entry points run: the Orchestrator's dispatch (`orchestrator2/registry.py`) and
the standalone socket (`strategy_agent_api.py`).
"""
from __future__ import annotations

from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.modernization_common.restore_tool import make_compare_tool, make_restore_tool
from agents_orchestrator.strategy_agent.prompts.strategy_prompt import STRATEGY_SYS_MESSAGE
from agents_orchestrator.strategy_agent.tools.strategy_tools import TOOLS
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools

AGENT_ID = "strategy"

#: The platform's document system bound to THIS stage (see discovery_agent/agents/assessor.py).
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

#: Going back to an earlier plan from the chat (research §12.4) — the page's Restore, too.
VERSION_TOOLS = [make_compare_tool(AGENT_ID, "migration plan"), make_restore_tool(AGENT_ID, "migration plan")]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *DOCUMENT_TOOLS, *VERSION_TOOLS],
                             checkpoint_name=AGENT_ID)

__all__ = ["AGENT_ID", "DOCUMENT_TOOLS", "STRATEGY_SYS_MESSAGE", "TOOLS", "VERSION_TOOLS", "app"]
