"""`restore_version(version, reason)` — going back to an earlier version from the chat.

Research §12.4 and the "GOING BACK" prompt rule: when the user asks to go back ("use version 2
of the brief"), the agent shows what differs, asks them to confirm, then calls this. It is the
same operation as the page's Restore button (`shared/services/version_lineage.restore_version`):

  - it creates a NEW draft version with the earlier content (`restored_from`, the reason) and
    never deletes or rewrites one;
  - the user is its producer, so someone else approves it (owner or Project Admin fallback),
    and restoring someone else's work does not let THEM approve it either (`producers_of`);
  - what was built on the version in force will show as out of date once the restored copy
    is approved — the reply names those agents, so the user is told before, not after.

PAGE CHATS ONLY, like `versions.freeze_version`: an Orchestrator conversation's deliverables are
not the agent pages' history, so there is nothing of the page's to restore from there.

`make_restore_tool(stage, noun)` builds the tool for one agent: each Track 3 agent binds its own.
"""
from __future__ import annotations

import logging

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

_LABEL = {
    "requirements_modernization": "Migration Intent", "discovery": "Dependency and Risk",
    "design_modernization": "Target Architecture", "strategy": "Migration Strategy",
    "testing_modernization": "Equivalence Testing", "development_modernization": "Migration Development",
    "code_review_modernization": "Migration Review", "security_modernization": "Security (Modernization)",
    "deployment_modernization": "Cutover", "documentation_modernization": "Cutover Pack",
}


async def restore(stage: str, noun: str, version: int, reason: str) -> str:
    from config.ws_helper import get_orchestrator_run, get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    if get_orchestrator_run():
        return (f"Restoring is done on the {_LABEL.get(stage, stage)} page, where the {noun}'s versions live — "
                "an Orchestrator conversation has its own deliverables, not the page's history.")
    project_id, tenant_id, user_id = get_project_id(), get_tenant_id(), get_user_id()
    if not (project_id and tenant_id and user_id):
        return "Not restored: this conversation is not attached to a project and a signed-in user."

    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415
    from shared.services import version_lineage as lineage  # noqa: PLC0415

    try:
        async with get_db_session_for_tenant(str(tenant_id)) as db:
            current = await svc.latest_published(db, str(project_id), stage)
            ref = await lineage.restore_version(db, tenant_id=str(tenant_id), project_id=str(project_id),
                                                stage=stage, version=int(version), restorer=str(user_id),
                                                reason=reason)
            consumers = (await svc.version_consumers(db, str(project_id), stage, current.version)
                         if current is not None else [])
    except lineage.RestoreRefused as exc:
        return f"Not restored: {exc}."
    except Exception as exc:  # noqa: BLE001 — the user must hear it failed, and why in general terms
        logger.exception("restore_version failed (%s v%s)", stage, version)
        return f"Not restored ({type(exc).__name__}). Nothing was changed."

    later = sorted({_LABEL.get(c["consumerStage"], c["consumerStage"]) for c in consumers})
    stale = (f" Once it is approved, what was built on v{current.version} will show as out of date: "
             + ", ".join(later) + "." if later else
             (f" Nothing has been built on v{current.version} yet, so nothing goes out of date." if current else ""))
    return (f"Restored {noun} v{version} as v{ref.version} — a NEW draft with v{version}'s content (reason recorded: "
            f"\"{reason.strip()}\"). Nothing was deleted or overwritten. It needs approval again, by someone who "
            f"did not produce it or v{version}.{stale}")


async def compare(stage: str, noun: str, older: int, newer: int) -> str:
    """What differs between two versions, as short lines the agent can show the user."""
    from config.ws_helper import get_project_id, get_tenant_id  # noqa: PLC0415

    project_id, tenant_id = get_project_id(), get_tenant_id()
    if not (project_id and tenant_id):
        return "Cannot compare: this conversation is not attached to a project."
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import version_lineage as lineage  # noqa: PLC0415

    try:
        async with get_db_session_for_tenant(str(tenant_id)) as db:
            result = await lineage.compare_versions(db, str(project_id), stage, int(older), int(newer))
    except lineage.RestoreRefused as exc:
        return f"Cannot compare: {exc}."
    except Exception as exc:  # noqa: BLE001 — the user must hear it failed; nothing was changed
        logger.exception("compare_versions failed (%s v%s → v%s)", stage, older, newer)
        return f"Cannot compare ({type(exc).__name__}). Nothing was changed."
    diffs = result.get("differences") or []
    if not diffs:
        return f"{noun.capitalize()} v{older} and v{newer} have the same content."
    shown = diffs[:_COMPARE_LINES]
    lines = [f"- {d['path']}: " + (f"{d['before']!r} → {d['after']!r}" if d["change"] == "changed"
             else f"{d['change']} {d['after'] if d['change'] == 'added' else d['before']!r}") for d in shown]
    more = [f"…and {len(diffs) - len(shown)} more difference(s)."] if len(diffs) > len(shown) else []
    return _NL.join([f"{noun.capitalize()} v{older} → v{newer}, {len(diffs)} difference(s):", *lines, *more])


_COMPARE_LINES = 25
_NL = chr(10)


def make_compare_tool(stage: str, noun: str) -> StructuredTool:
    async def compare_versions(older: int, newer: int) -> str:
        return await compare(stage, noun, older, newer)

    compare_versions.__doc__ = (f"What differs between two {noun} versions (older, newer). Use it to show the "
                                "user the change before restoring an earlier version.")
    return StructuredTool.from_function(coroutine=compare_versions, name="compare_versions")


def make_restore_tool(stage: str, noun: str) -> StructuredTool:
    async def restore_version(version: int, reason: str) -> str:
        return await restore(stage, noun, version, reason)

    restore_version.__doc__ = (
        f"Bring an earlier {noun} version back as a NEW draft version (nothing is deleted).\n\n"
        f"Only after showing the user what differs between that version and the current one and "
        f"getting their confirmation. `reason` is the user's reason, in their words; required.")
    return StructuredTool.from_function(coroutine=restore_version, name="restore_version")
