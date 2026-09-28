"""The project's approved tech stack, as Track 3 agents read it.

Agent Studio lets a Business Unit or a project choose an approved stack
(`shared/services/tech_stack_store.py`: the project's selection, else the BU default, else
none, always with its source). Track 1's Design, Development and Deployment agents follow
it; Track 3's recommending agents must too (Lessons §3, §7.2 #4) — Migration Intent now,
Target Architecture next:

  * the stack is authoritative for WHICH technologies are approved;
  * versions are still the agent's to give, and must be supported ones;
  * a recommendation outside the stack is allowed only as a stated DEPARTURE with a reason
    (Target Architecture records each as an ADR).

A TOOL, NOT A PROMPT BLOCK. Track 1's Design injects the stack into its generation prompt.
A Track 3 agent RECOMMENDS a target, so it must read the stack before recommending; as a
tool the read is identical on the standalone socket and under the Orchestrator (R1), and
the answer — including "no stack; recommend freely" and a stale-selection warning — is
said out loud rather than silently absent.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

#: How each source reads to a person. Mirrors `shared.services.tech_stack.SOURCE_LABELS`
#: and adds the one it has no label for.
SOURCE_TEXT = {
    "project_selection": "chosen for this project",
    "bu_default": "the Business Unit default",
    "none": "no approved stack",
    # Not "none": a stack that could not be READ is unknown, and a signed brief must be
    # able to tell "the project had no rule" from "we could not see the rule".
    "unreadable": "could not be read",
}


async def effective_stack() -> dict:
    """{name, source, source_text, categories, notes, warning} for the turn's project.

    Never raises: a stack that cannot be read is reported as such, with source "none" and
    the reason as the warning — the agent then says it, rather than recommending as if
    the project had no rule.
    """
    try:
        from shared.services import tech_stack_store  # noqa: PLC0415

        eff = await tech_stack_store.current_project_tech_stack()
    except Exception as exc:  # noqa: BLE001
        logger.warning("tech stack read failed: %s", type(exc).__name__)
        return {"name": None, "source": "unreadable", "source_text": SOURCE_TEXT["unreadable"],
                "categories": {}, "notes": "",
                "warning": "The project's tech stack could not be read, so this recommendation does not follow one."}
    if eff is None:
        return {"name": None, "source": "none", "source_text": SOURCE_TEXT["none"],
                "categories": {}, "notes": "", "warning": "This conversation is not attached to a project."}
    stack = eff.stack
    return {
        "name": stack.name if stack else None,
        "source": eff.source,
        "source_text": SOURCE_TEXT.get(eff.source, eff.source),
        "categories": dict(stack.categories) if stack else {},
        "notes": stack.notes if stack else "",
        "warning": eff.warning,
    }


def describe(stack: dict) -> str:
    """The stack as the agent reads it."""
    lines: list[str] = []
    if stack.get("name"):
        lines.append(f'This project\'s approved tech stack is "{stack["name"]}" ({stack["source_text"]}).')
        for category, items in (stack.get("categories") or {}).items():
            if items:
                lines.append(f"- {category}: {', '.join(map(str, items))}")
        if stack.get("notes"):
            lines.append(f"Notes: {stack['notes']}")
        lines.append(
            "Recommend within these technologies. Choose exact, supported versions yourself. "
            "Anything outside the stack is a DEPARTURE: say so to the user with the reason, and "
            "record it in stack_departures when you record.")
    elif stack.get("source") == "unreadable":
        lines.append("The project's approved tech stack could not be read. Say so to the user; do not "
                     "treat it as 'no stack applies'.")
    else:
        lines.append("This project has no approved tech stack, so recommend the target freely "
                     "(and say that no stack applies).")
    if stack.get("warning"):
        lines.append(f"Tell the user: {stack['warning']}")
    return "\n".join(lines)


@tool
async def get_project_tech_stack() -> str:
    """The project's approved tech stack (from Agent Studio) and where it comes from: chosen
    for this project, the Business Unit default, or none. Call it before recommending a
    target stack."""
    return describe(await effective_stack())


def applied_stack(stack: dict, departures: Optional[list[Any]]) -> dict:
    """What a recorded brief keeps about the stack: set by code from `effective_stack`,
    with only the stated departures coming from the model."""
    return {
        "name": stack.get("name"),
        "source": stack.get("source") or "none",
        "warning": stack.get("warning"),
        "departures": [str(d).strip() for d in (departures or []) if str(d).strip()],
    }
