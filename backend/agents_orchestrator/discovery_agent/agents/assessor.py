"""The Dependency and Risk agent's graph (Track 3 — Code Modernization).

`app` is what both entry points run: the Orchestrator's dispatch (through
`orchestrator2/registry.py`) and the standalone socket (`discovery_agent_api.py`).
"""
from __future__ import annotations

from agents_orchestrator.discovery_agent.prompts.discovery_prompt import DISCOVERY_SYS_MESSAGE
from agents_orchestrator.discovery_agent.tools.assessment_tools import TOOLS
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools
from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.modernization_common.restore_tool import make_compare_tool, make_restore_tool

AGENT_ID = "discovery"

#: The platform's document system, bound to THIS stage (never a tool argument, or a prompt
#: could claim another agent): `list_project_documents` / `read_document` read the project's
#: APPROVED documents — for a modernization, its legacy specs, runbooks and data
#: dictionaries — and every read is recorded as evidence; `raise_document_for_approval`
#: puts this agent's own draft document forward, exactly like the Documents panel's button.
#: Binding the reader also makes the standalone prompt layer add the approved-documents
#: block (`has_document_tools`), so the prompt only names tools that are really bound.
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

#: Going back to an earlier assessment from the chat (research §12.4): compare first, then
#: restore as a NEW draft. The page's Restore button is the same operation.
VERSION_TOOLS = [make_compare_tool(AGENT_ID, "assessment"), make_restore_tool(AGENT_ID, "assessment")]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *DOCUMENT_TOOLS, *VERSION_TOOLS],
                             checkpoint_name=AGENT_ID)

__all__ = ["DOCUMENT_TOOLS", "AGENT_ID", "DISCOVERY_SYS_MESSAGE", "TOOLS", "VERSION_TOOLS", "app"]
