"""The Equivalence Testing agent's graph (Track 3 — Code Modernization, Phase G: Baseline mode).

`app` is what both entry points run: the Orchestrator's dispatch (`orchestrator2/registry.py`) and
the standalone socket (`testing_modernization_agent_api.py`).
"""
from __future__ import annotations

from agents_orchestrator.modernization_common import legacy_code
from agents_orchestrator.modernization_common.graph import build_tool_agent_graph
from agents_orchestrator.modernization_common.restore_tool import make_compare_tool, make_restore_tool
from agents_orchestrator.testing_modernization_agent.prompts.equivalence_prompt import EQUIVALENCE_SYS_MESSAGE
from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import TOOLS
from shared.tools.document_approval import make_approval_tools
from shared.tools.project_documents import make_document_tools

AGENT_ID = "testing_modernization"

#: The platform's document system bound to THIS stage.
DOCUMENT_TOOLS = [*make_document_tools(AGENT_ID), *make_approval_tools(AGENT_ID)]

#: Going back to an earlier baseline from the chat (research §12.4) — the page's Restore, too.
VERSION_TOOLS = [make_compare_tool(AGENT_ID, "baseline"), make_restore_tool(AGENT_ID, "baseline")]

#: The legacy code, read-only: the profile is drafted from it; pulling it needs this stage's connection.
LEGACY_TOOLS = [legacy_code.get_legacy_code_profile, legacy_code.list_legacy_files, legacy_code.read_legacy_file,
                legacy_code.search_legacy_code, *legacy_code.pull_tools(AGENT_ID)]

app = build_tool_agent_graph(agent_type=AGENT_ID, tools=[*TOOLS, *LEGACY_TOOLS, *DOCUMENT_TOOLS, *VERSION_TOOLS],
                             checkpoint_name=AGENT_ID)

__all__ = ["AGENT_ID", "DOCUMENT_TOOLS", "EQUIVALENCE_SYS_MESSAGE", "LEGACY_TOOLS", "TOOLS", "VERSION_TOOLS", "app"]
