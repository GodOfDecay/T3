"""The Migration Review agent's graph (Track 3 — Code Modernization, Phase I).

`app` is what both entry points run: the Orchestrator's dispatch (`orchestrator2/registry.py`) and
the standalone socket (`code_review_modernization_agent_api.py`).
"""
from __future__ import annotations

from agents_orchestrator.code_review_modernization_agent.prompts.review_prompt import (
    MIGRATION_REVIEW_SYS_MESSAGE,
)
from agents_orchestrator.code_review_modernization_agent.tools.review_tools import TOOLS
from agents_orchestrator.modernization_common import legacy_code
from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.modernization_common.restore_tool import make_compare_tool, make_restore_tool
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools

AGENT_ID = "code_review_modernization"

#: The platform's document system bound to THIS stage.
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

#: Going back to an earlier migration review from the chat (research §12.4) — the page's Restore, too.
VERSION_TOOLS = [make_compare_tool(AGENT_ID, "migration review"), make_restore_tool(AGENT_ID, "migration review")]

#: The legacy code, READ-ONLY. Pulling needs this stage's connection; nothing here writes it. The
#: side-by-side reads that count as "files read" are the tools' own (`read_legacy_counterpart`).
LEGACY_TOOLS = [legacy_code.get_legacy_code_profile, legacy_code.list_legacy_files,
                legacy_code.search_legacy_code, *legacy_code.pull_tools(AGENT_ID)]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *LEGACY_TOOLS, *DOCUMENT_TOOLS, *VERSION_TOOLS],
                             checkpoint_name=AGENT_ID)

__all__ = ["AGENT_ID", "DOCUMENT_TOOLS", "LEGACY_TOOLS", "MIGRATION_REVIEW_SYS_MESSAGE", "TOOLS",
           "VERSION_TOOLS", "app"]
