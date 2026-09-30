"""The upstream work a Track 3 agent builds on — THE ONE reader, shared by every agent from 3 on.

WHICH VERSION. On an agent page: exactly the versions THIS TURN pinned
(`versions.turn_built_from`, noted by `standalone.upstream_from_pages` as it read them — the page's
approved version, or, where the project does not enforce publication, its newest draft, labelled
so). In an Orchestrator conversation: the conversation's own run columns, which is self-contained
like everything the Orchestrator records.

WHAT COMES BACK. Each input as stored (for detail tools), its version and status, and its
HAND-OVER PACKET payload — validated by the packet models, so an agent reasons over the same
contract the next agent will receive, and a gap is said in plain words (`emit`), never guessed.

    inputs = await read_inputs(["requirements_modernization", "discovery", "design_modernization"])
    inputs["discovery"].packet   -> dict | None
    missing_line(inputs["discovery"])  -> why it cannot be used, in words
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

#: stage → (noun, the page that makes it)
NOUNS = {
    "requirements_modernization": ("migration-intent brief", "brief", "Migration Intent"),
    "discovery": ("Dependency and Risk assessment", "assessment", "Dependency and Risk"),
    "design_modernization": ("target design", "target design", "Target Architecture"),
    "strategy": ("migration plan", "migration plan", "Migration Strategy"),
}


@dataclass
class Input:
    """One upstream artifact as this turn read it."""

    stage: str
    stored: Optional[dict] = None      # as the page stores it
    version: Optional[int] = None      # None in an Orchestrator conversation
    status: str = "draft"              # the version store's vocabulary; "granted" = by exception
    packet: Optional[dict] = None      # the validated hand-over payload
    problems: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        noun = NOUNS.get(self.stage, (self.stage, self.stage, self.stage))[1]
        if self.version is None:
            return f"the {noun} recorded in this conversation"
        state = {"published": "approved", "granted": "approved by exception"}.get(self.status, "not yet approved")
        return f"{noun} v{self.version} ({state})"


def _builder(stage: str):
    from agents_orchestrator.modernization_common.handover import emit  # noqa: PLC0415

    return {"requirements_modernization": emit.brief_packet, "discovery": emit.assessment_packet,
            "design_modernization": emit.design_packet, "strategy": emit.plan_packet}[stage]


def _fill(item: Input, stored: dict, envelope: dict) -> None:
    item.stored = stored
    built = _builder(item.stage)(stored, envelope)
    item.packet = built.packet.payload.model_dump(mode="json", by_alias=True) if built.ok else None
    item.problems = built.problems


async def read_inputs(stages: list[str]) -> dict[str, Input]:
    from agents_orchestrator.modernization_common.handover.emit import envelope_of  # noqa: PLC0415
    from config.ws_helper import get_orchestrator_run, get_project_id, get_run_id, get_tenant_id  # noqa: PLC0415

    out = {s: Input(s) for s in stages}
    tenant_id, project_id = get_tenant_id(), get_project_id()
    if not (tenant_id and project_id):
        return out
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415

    try:
        async with get_db_session_for_tenant(str(tenant_id)) as db:
            if get_orchestrator_run():
                run_id = get_run_id()
                if run_id:
                    from sqlalchemy import select  # noqa: PLC0415

                    from shared.models.orm import Run  # noqa: PLC0415
                    from shared.services.artifact_service import _COLUMN_MAP  # noqa: PLC0415

                    columns = [getattr(Run, _COLUMN_MAP[s]) for s in stages]
                    row = (await db.execute(select(*columns).where(Run.id == str(run_id)))).first()
                    if row is not None:
                        for stage, stored in zip(stages, row):
                            if stored:
                                _fill(out[stage], stored, {"version": 1, "status": "draft"})
                return out
            from agents_orchestrator.modernization_common.versions import turn_built_from  # noqa: PLC0415
            from shared.services import artifact_versions as svc  # noqa: PLC0415

            for pin in turn_built_from() or []:
                stage = pin.get("stage")
                if stage not in out or not pin.get("version"):
                    continue
                row = await svc.get_version(db, str(project_id), stage, int(pin["version"]))
                if row is None or not row.payload:
                    continue
                item = out[stage]
                item.version = row.version
                item.status = "granted" if pin.get("status") == "granted" else row.status
                _fill(item, row.payload, envelope_of(row))
    except Exception:  # noqa: BLE001 — said to the agent, never taken as "nothing recorded"
        logger.exception("modernization: reading upstream work failed (project %s)", project_id)
        for item in out.values():
            item.problems = ["It could not be read just now (a database error). Try again."]
    return out


def missing_line(item: Input) -> str:
    """Why an input cannot be used, in words the agent passes on."""
    noun, _short, page = NOUNS.get(item.stage, (item.stage, item.stage, item.stage))
    if item.problems and item.stored:
        return f"The {item.label} cannot be used: " + " ".join(item.problems[:5]) + f" It is fixed on the {page} page."
    if item.problems:
        return f"The {noun} could not be read: {item.problems[0]}"
    return (f"There is no {noun} to work from yet (or the project only builds on approved work and none is "
            f"approved). It is made on the {page} page, and approved there.")
