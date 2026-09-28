"""Restore, compare and staleness for stage versions (Track 3 backbone, research §12.4, §5.3).

Mounted under `/artifact-versions` beside `artifact_versions_router`, with the same
project-scope dependency on every route (`require_project_access`, which reads the project
from the PATH — every route here has `{project_id}` in its path, so the floor is real, not
the no-op it becomes on a project-less route: Lessons R11).

    POST {project}/stages/{stage}/versions/{v}/restore   run:create   a NEW draft = v's content
    GET  {project}/stages/{stage}/compare?from=&to=     artifact:view  what differs
    GET  {project}/stages/{stage}/versions/{v}/staleness artifact:view  inputs with a newer published version

Restoring is PRODUCING (the same permission as running the agent): the restorer becomes the
new version's producer, and the schema's self-publication check stops them approving it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.authz.dependency import require_permission
from shared.authz.project_scope import require_project_access
from shared.db import get_db_session
from shared.services import artifact_versions as svc
from shared.services import version_lineage as lineage

version_lineage_router = APIRouter(dependencies=[Depends(require_project_access())])


class RestoreBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


async def _known(db: AsyncSession, project_id: str, stage: str) -> None:
    """Track 3 stages on Code Modernization projects only. Track 1 never had restore, and a
    route that let `run:create` mint new versions of Track 1 stages would be a new way to
    produce them outside their agents."""
    from shared.services.repository_roles import TRACK3_STAGES  # noqa: PLC0415

    try:
        svc.assert_known_stage(stage)
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    track = (await db.execute(text("SELECT track FROM projects WHERE id = CAST(:p AS uuid)"),
                              {"p": project_id})).scalar_one_or_none()
    if stage not in TRACK3_STAGES or track != "modernization":
        raise HTTPException(status_code=404, detail=f"{stage} has no version history actions on this project")


@version_lineage_router.post(
    "/{project_id}/stages/{stage}/versions/{version}/restore",
    dependencies=[Depends(require_permission("run:create"))],
)
async def restore_stage_version(project_id: str, stage: str, version: int, body: RestoreBody,
                                request: Request, db: AsyncSession = Depends(get_db_session)):
    """Bring an earlier version back as a new draft. The reason is required and recorded."""
    await _known(db, project_id, stage)
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    if not tenant_id or not user_id:
        raise HTTPException(status_code=401, detail="Sign in to restore a version.")
    # Restoring PRODUCES a version of this stage, so it needs the same reach running the
    # stage's agent does — `run:create` alone is a tenant-wide union.
    from shared.authz.agent_access import resolve_involvement  # noqa: PLC0415
    from shared.authz.effective_role import effective_platform_role  # noqa: PLC0415

    reach = await resolve_involvement(db, tenant_id=str(tenant_id), project_id=project_id,
                                      role=await effective_platform_role(db, request), user_id=str(user_id),
                                      agent_id=stage)
    if reach == "none":
        raise HTTPException(status_code=403, detail="Your role does not reach this agent on this project.")
    try:
        ref = await lineage.restore_version(db, tenant_id=str(tenant_id), project_id=project_id, stage=stage,
                                            version=version, restorer=str(user_id), reason=body.reason)
    except lineage.RestoreRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"stage": stage, "version": ref.version, "status": ref.status, "restoredFrom": version,
            "note": "The restored copy is a new draft and needs approval by someone other than you."}


@version_lineage_router.get(
    "/{project_id}/stages/{stage}/compare",
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def compare_stage_versions(project_id: str, stage: str,
                                 from_: int = Query(alias="from", ge=1), to: int = Query(ge=1),
                                 db: AsyncSession = Depends(get_db_session)):
    await _known(db, project_id, stage)
    try:
        return await lineage.compare_versions(db, project_id, stage, from_, to)
    except lineage.RestoreRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@version_lineage_router.get(
    "/{project_id}/stages/{stage}/versions/{version}/staleness",
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def stage_version_staleness(project_id: str, stage: str, version: int,
                                  db: AsyncSession = Depends(get_db_session)):
    """Whether any input this version was built from now has a newer APPROVED version.
    `pinned: false` means the version recorded no inputs — "not known", not "fresh"."""
    await _known(db, project_id, stage)
    row = await svc.get_version(db, project_id, stage, version)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
    stale = await lineage.stale_inputs(db, project_id, row.built_from)
    return {"stage": stage, "version": version, "pinned": row.built_from is not None,
            "stale": bool(stale), "inputs": stale}
