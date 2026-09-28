"""Every recorded brief and assessment becomes a numbered, frozen version.

The run column (`migration_intent_payload`, `discovery_artifacts`) is overwritten on each
record — the standalone chat reuses one run per project and agent — so on its own it
keeps only the latest. Freezing each record as a stage version (the `artifact_versions`
store behind Track 1's sign-off) gives the pages their history, and the BA's approval
its unit: a version, not whatever the column happens to hold when someone clicks
Approve.

NOT FROM THE ORCHESTRATOR. An Orchestrator conversation is self-contained: what its
agents record is that conversation's Deliverables, and is not added to the agent pages'
history. Only a page's chat freezes versions.

Non-fatal by design. The user already has the brief or report in front of them; a
version that could not be written is logged and reported in the tool's reply, never
raised through the turn.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: The input versions THIS TURN read (research §5.3, `built_from`), noted by
#: `standalone.upstream_from_pages` as it reads each one and stamped on any version the turn
#: freezes. Set per turn and cleared at its end, so a pin never leaks into the next turn.
_BUILT_FROM: ContextVar[Optional[list]] = ContextVar("track3_built_from", default=None)


def note_input(*, artifact: str, stage: str, version: int, status: str) -> None:
    """Record that this turn built on `stage` v`version` (a published or draft read)."""
    pins = [p for p in (_BUILT_FROM.get() or []) if p.get("stage") != stage]
    _BUILT_FROM.set([*pins, {"artifact": artifact, "stage": stage, "version": version, "status": status}])


def turn_built_from() -> Optional[list]:
    return _BUILT_FROM.get()


def reset_built_from() -> None:
    _BUILT_FROM.set(None)


async def freeze_version(stage: str, payload: Any, built_from: Optional[list] = None) -> Optional[int]:
    """Freeze `payload` as the next version of `stage` on this turn's project, produced
    by this turn's user, pinned to what it was built from (`built_from`, else the inputs
    this turn read — `turn_built_from`). Returns the version number, or None when it could
    not be written (no project or user bound, or the store refused)."""
    from config.ws_helper import (  # noqa: PLC0415
        get_orchestrator_run,
        get_project_id,
        get_run_id,
        get_tenant_id,
        get_user_id,
    )

    if get_orchestrator_run():
        return None
    tenant_id, project_id, user_id = get_tenant_id(), get_project_id(), get_user_id()
    if not (tenant_id and project_id and user_id):
        return None
    try:
        from shared.db import get_db_session_for_tenant  # noqa: PLC0415
        from shared.services import artifact_versions as svc  # noqa: PLC0415

        frozen = json.loads(json.dumps(payload, default=str))
        async with get_db_session_for_tenant(str(tenant_id)) as db:
            ref = await svc.snapshot_stage_payload(
                db, tenant_id=str(tenant_id), project_id=str(project_id), stage=stage,
                payload=frozen, produced_by=str(user_id),
                run_id=str(get_run_id()) if get_run_id() else None,
                # A page freeze always records its inputs: [] when the turn read nothing
                # upstream (a first-stage agent), so "pinned nothing" is distinguishable
                # from a pre-0068 version, whose built_from is NULL ("not known").
                built_from=built_from if built_from is not None else (turn_built_from() or []),
            )
        return ref.version
    except Exception:  # noqa: BLE001
        logger.exception("modernization: freezing a %s version failed (project %s)", stage, project_id)
        return None


def saved_line(saved: str, version: Optional[int], noun: str) -> str:
    """The tool reply's status line: the run save, plus the version it became."""
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run() and saved.startswith("Saved"):
        return f"Recorded in this Orchestrator conversation — the {noun} is in its Deliverables."
    if version is None:
        return saved
    return f"{saved} Recorded as {noun} v{version} (draft) — it is listed on the agent's page."
