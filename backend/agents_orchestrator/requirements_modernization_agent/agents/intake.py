"""The Migration Intent agent's graph (Track 3 — Code Modernization).

A separate agent from Portfolio 1's `requirements` — its own id, prompt, tools and output
column — because Track 3 is its own portfolio (help/multi-track-agent-access-design.md
§1.4) and its work product is a migration-intent brief, not a story backlog.
"""
from __future__ import annotations

from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.requirements_modernization_agent.prompts.migration_intent_prompt import (
    MIGRATION_INTENT_SYS_MESSAGE,
)
from agents_orchestrator.requirements_modernization_agent.tools.brief_tools import TOOLS
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools

AGENT_ID = "requirements_modernization"

#: The platform's document system, bound to THIS stage (never a tool argument, or a prompt
#: could claim another agent): `list_project_documents` / `read_document` read the project's
#: APPROVED documents — for a modernization, its legacy specs, runbooks and data
#: dictionaries — and every read is recorded as evidence; `raise_document_for_approval`
#: puts this agent's own draft document forward, exactly like the Documents panel's button.
#: Binding the reader also makes the standalone prompt layer add the approved-documents
#: block (`has_document_tools`), so the prompt only names tools that are really bound.
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *DOCUMENT_TOOLS], checkpoint_name=AGENT_ID)

__all__ = ["DOCUMENT_TOOLS", "AGENT_ID", "MIGRATION_INTENT_SYS_MESSAGE", "TOOLS", "app"]
