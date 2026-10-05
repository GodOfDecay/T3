"""The Programme view of a Code Modernization project (Track 3, Phase C item 7).

Mounted under `/modernization-programme` with the project-scope dependency on every route
(`require_project_access` — every route has `{project_id}` in its path, so the floor is real:
Lessons R11), and every route refuses a project that is not on the Code Modernization track.

    GET {project}/ledger                   artifact:view    the module ledger, one row per module
    GET {project}/repositories             artifact:view    legacy and target repositories
    PUT {project}/repositories/{role}      project:update   name the legacy or the target repository
    GET {project}/approval-settings        artifact:view    fallback mode, policy, staffing warnings
    PUT {project}/approval-settings        project:update   change fallback mode / policy

WHO WRITES. `project:update` alone is tenant-wide (bu_admin and project_admin hold it), so
each write also requires that the caller ADMINISTERS THIS project
(`assert_can_administer_project`, the same rule PATCH /projects/{id} uses). Naming the
repositories is the Project Admin's own job (Track 3 master plan §3), so it applies directly
rather than going through the Business Unit Admin request lane PATCH /projects uses for
budget and name.

NO COMMIT HERE beyond the session's own (Lessons R23): the services flush, the session
dependency commits.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit.models import AuditEventPayload
from shared.audit.service import audit_service
from shared.authz.dependency import require_permission
from shared.authz.project_scope import assert_can_administer_project, require_project_access
from shared.db import get_db_session
from shared.services import fallback_approval as fb
from shared.services import modernization_ledger as ledger
from shared.services import repository_roles as rr

modernization_programme_router = APIRouter(dependencies=[Depends(require_project_access())])

TRACK = "modernization"


class RepositoryBody(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    branch: str = Field(default="", max_length=255)


class ApprovalSettingsBody(BaseModel):
    fallbackMode: Literal["always", "after_sla"]
    policy: Literal["standard", "pilot", "strict"]


async def _modernization_project(db: AsyncSession, request: Request, project_id: str) -> tuple[str, str]:
    """(project_id, tenant_id) once the project is a Code Modernization project.

    404 for any other track — this view does not exist on a Greenfield project, and the
    project's existence was already established by the router's scope dependency."""
    tenant_id = str(getattr(request.state, "tenant_id", "") or "")
    project = getattr(request.state, "project", None)
    resolved = str(getattr(project, "id", None) or project_id)
    track = (await db.execute(text("SELECT track FROM projects WHERE id = CAST(:p AS uuid)"),
                              {"p": resolved})).scalar_one_or_none()
    if track != TRACK:
        raise HTTPException(status_code=404, detail="This is not a Code Modernization project.")
    return resolved, tenant_id


async def _administered(db: AsyncSession, request: Request, project_id: str) -> tuple[str, str, str]:
    resolved, tenant_id = await _modernization_project(db, request, project_id)
    await assert_can_administer_project(db, request, request.state.project)
    user_id = str(getattr(request.state, "user_id", "") or "")
    return resolved, tenant_id, user_id


@modernization_programme_router.get(
    "/{project_id}/ledger", dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_ledger(project_id: str, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Every module and where it stands. `states` is the fixed order the board draws its
    columns in, so an empty ledger still says what the columns are."""
    resolved, _ = await _modernization_project(db, request, project_id)
    rows = await ledger.list_modules(db, resolved)
    return {"projectId": resolved, "states": list(ledger.STATES), "modules": [ledger.as_dict(r) for r in rows]}


class LedgerActionBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    toMigrating: bool = False


@modernization_programme_router.post(
    "/{project_id}/ledger/{module_id}/{action}", dependencies=[Depends(require_permission("artifact:view"))],
)
async def ledger_action(project_id: str, module_id: str, action: Literal["unblock", "reopen"], body: LedgerActionBody,
                        request: Request, db: AsyncSession = Depends(get_db_session)):
    """A person moves a module the agents cannot (research §12.4): UNBLOCK a blocked module (back to where it
    was, or to migrating for rework; the rejection count restarts) or REOPEN a verified / cut-over one for
    rework. An Architect or a Project Admin OF THIS PROJECT, with a reason; audited. Without this a module
    rejected three times stayed blocked for ever."""
    from shared.services.fallback_approval import project_roles  # noqa: PLC0415

    resolved, tenant_id = await _modernization_project(db, request, project_id)
    user_id = str(getattr(request.state, "user_id", "") or "")
    roles = await project_roles(db, tenant_id=tenant_id, project_id=resolved, user_id=user_id)
    role = "project_admin" if "project_admin" in roles else ("architect" if "architect" in roles else None)
    if role is None:
        raise HTTPException(status_code=403, detail="Only an Architect or a Project Admin of this project unblocks or reopens a module.")
    try:
        if action == "unblock":
            row = await ledger.unblock(db, project_id=resolved, module_id=module_id, role=role, reason=body.reason,
                                       actor=user_id or None, to_migrating=body.toMigrating)
        else:
            row = await ledger.reopen(db, project_id=resolved, module_id=module_id, role=role, reason=body.reason,
                                      actor=user_id or None)
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await audit_service.emit(AuditEventPayload(
        tenant_id=tenant_id, event_type=f"modernization.module_{action}ed", actor_id=user_id or None,
        resource_type="project", resource_id=resolved,
        payload={"moduleId": module_id, "reason": body.reason, "state": row.state, "role": role},
    ))
    return ledger.as_dict(row)


@modernization_programme_router.get(
    "/{project_id}/repositories", dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_repositories(project_id: str, request: Request, db: AsyncSession = Depends(get_db_session)):
    resolved, _ = await _modernization_project(db, request, project_id)
    roles = await rr.get_roles(db, resolved)
    return {"projectId": resolved, "legacy": rr.as_dict(roles["legacy"]) if "legacy" in roles else None,
            "target": rr.as_dict(roles["target"]) if "target" in roles else None}


@modernization_programme_router.put(
    "/{project_id}/repositories/{role}", dependencies=[Depends(require_permission("project:update"))],
)
async def put_repository(project_id: str, role: Literal["legacy", "target"], body: RepositoryBody,
                         request: Request, db: AsyncSession = Depends(get_db_session)):
    """Name the project's legacy or target repository. Refused (400) for a non-https URL, an
    unsupported host, or a target that is the legacy repository."""
    resolved, tenant_id, user_id = await _administered(db, request, project_id)
    try:
        row = await rr.set_role(db, tenant_id=tenant_id, project_id=resolved, role=role, url=body.url,
                                branch=body.branch, actor=user_id)
    except rr.RepositoryRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.refresh(row)
    await audit_service.emit(AuditEventPayload(
        tenant_id=tenant_id, event_type="modernization.repository_set", actor_id=user_id or None,
        resource_type="project", resource_id=resolved,
        payload={"role": role, "url": row.url, "branch": row.branch},
    ))
    return rr.as_dict(row)


async def _settings(db: AsyncSession, tenant_id: str, project_id: str) -> dict:
    mode, policy = (await db.execute(text(
        "SELECT approval_fallback_mode, approval_policy FROM projects WHERE id = CAST(:p AS uuid)"),
        {"p": project_id})).one()
    return {"projectId": project_id, "fallbackMode": mode, "policy": policy,
            "warnings": await fb.staffing_warnings(db, tenant_id=tenant_id, project_id=project_id)}


@modernization_programme_router.get(
    "/{project_id}/approval-settings", dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_approval_settings(project_id: str, request: Request, db: AsyncSession = Depends(get_db_session)):
    resolved, tenant_id = await _modernization_project(db, request, project_id)
    return await _settings(db, tenant_id, resolved)


@modernization_programme_router.put(
    "/{project_id}/approval-settings", dependencies=[Depends(require_permission("project:update"))],
)
async def put_approval_settings(project_id: str, body: ApprovalSettingsBody, request: Request,
                                db: AsyncSession = Depends(get_db_session)):
    resolved, tenant_id, user_id = await _administered(db, request, project_id)
    before = await _settings(db, tenant_id, resolved)
    await db.execute(text(
        "UPDATE projects SET approval_fallback_mode = :m, approval_policy = :pol WHERE id = CAST(:p AS uuid)"),
        {"m": body.fallbackMode, "pol": body.policy, "p": resolved})
    # AUDITED, because the person these settings constrain is the one who may change them:
    # a Project Admin loosening Strict / after-SLA, approving as fallback and tightening it
    # again leaves this trail (before → after, who, when) beside the labelled approval.
    await audit_service.emit(AuditEventPayload(
        tenant_id=tenant_id, event_type="modernization.approval_settings_changed", actor_id=user_id or None,
        resource_type="project", resource_id=resolved,
        payload={"before": {"fallbackMode": before["fallbackMode"], "policy": before["policy"]},
                 "after": {"fallbackMode": body.fallbackMode, "policy": body.policy}},
    ))
    return await _settings(db, tenant_id, resolved)
