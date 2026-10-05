"""The publication gate for stage artifact versions — phase 2.

WHAT THIS IS FOR. Agents hand work to each other through `runs.{stage}_artifacts`, a
JSONB column written in place. Phase 1 added `artifact_versions`: frozen, numbered
snapshots that cannot change once created. These routes are how a human signs one off.

TWO CHECKS, chosen consciously — the same decision every gated router in this codebase
has to make:

  `require_project_access()` on the router says the caller reaches THIS project.
  `require_stage_approval()` on the decision routes says they may approve THIS STAGE —
  resolved per request from `_PHASE_PERMISSION[stage]`, because the permission differs
  by stage and one fixed string would let Requirements' approver sign off a deployment.

NOT `assert_can_administer_project`, which the blob-artifact gate uses. That demands
project administration, and these permissions are held by delivery roles — `architect`,
`qa`, `devops_engineer`, `scrum_master` — which are deliberately NOT project admins.
Requiring both would leave every stage permission granted to nobody who could use it,
which is exactly how `artifact:approve_deployment` came to look broken.

WHAT CONSUMERS READ is decided by `projects.enforce_artifact_publication` (phase 3),
off by default. With it off, agents read the working draft exactly as they always did.

`request-access` (phase 4) is the ONLY way past the gate, and it goes to a named human
rather than a flag: the owner of the producing stage decides, per version, per consumer.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.authz.dependency import require_permission, require_stage_approval
from shared.authz.project_scope import require_project_access
from shared.db import get_db_session
from shared.services import artifact_versions as svc
from shared.services.actor_labels import actor_labels, relabel

logger = logging.getLogger(__name__)

# Every route is scoped to its {project_id} by the router-level dependency.
artifact_versions_router = APIRouter(dependencies=[Depends(require_project_access())])


class VersionOut(BaseModel):
    """A version as the UI sees it.

    NAMED FIELDS, never `**row.__dict__`. The payload can be large and is not needed
    by a list view, and a spread would start shipping whatever column someone adds
    next — the same reasoning that keeps the PAT out of the prepared-deploy response.
    """
    id: str
    stage: str
    version: int
    status: str
    contentHash: str
    producedBy: str
    publishedBy: Optional[str] = None
    publishedAt: Optional[str] = None
    rejectionReason: Optional[str] = None
    covers: list = Field(default_factory=list)
    createdAt: Optional[str] = None
    runId: Optional[str] = None
    # 0068: provenance and the approver's capacity. Optional, so Track 1 rows (all NULL)
    # and clients that ignore them are unchanged.
    builtFrom: Optional[list] = None
    restoredFrom: Optional[int] = None
    restoreReason: Optional[str] = None
    approvedAs: Optional[str] = None
    fallbackReason: Optional[str] = None

    @classmethod
    def of(cls, row) -> "VersionOut":
        return cls(
            id=str(row.id), stage=row.stage, version=row.version, status=row.status,
            contentHash=row.content_hash, producedBy=row.produced_by,
            publishedBy=row.published_by,
            publishedAt=row.published_at.isoformat() if row.published_at else None,
            rejectionReason=row.rejection_reason, covers=list(row.covers or []),
            createdAt=row.created_at.isoformat() if row.created_at else None,
            runId=str(row.run_id) if row.run_id else None,
            builtFrom=getattr(row, "built_from", None),
            restoredFrom=getattr(row, "restored_from", None),
            restoreReason=getattr(row, "restore_reason", None),
            approvedAs=getattr(row, "approved_as", None),
            fallbackReason=getattr(row, "fallback_reason", None),
        )


class VersionDetailOut(VersionOut):
    """One version, with its frozen payload. Only on the single-version read."""
    payload: Any = None

    @classmethod
    def of(cls, row) -> "VersionDetailOut":
        base = VersionOut.of(row)
        return cls(**base.model_dump(), payload=row.payload)


class SnapshotBody(BaseModel):
    payload: Any = None
    runId: Optional[str] = None
    covers: list[str] = Field(default_factory=list)


class RejectBody(BaseModel):
    reason: str = Field(min_length=1)


class ConsumptionRequestBody(BaseModel):
    #: The stage that wants to read it. A BACKEND stage name.
    consumerStage: str = Field(min_length=1)
    #: Why the published version will not do. Required: the owner is being asked to
    #: vouch for unfinished or superseded work, and "please approve" is not an answer
    #: they can weigh.
    reason: str = Field(min_length=1)


def _refusal(exc: svc.PublicationRefused) -> HTTPException:
    """Map a refusal to the status that describes it.

    A 400 for everything would make "you cannot approve your own work" (403) look like
    a malformed request, and the UI could not tell them apart.
    """
    status = {
        "not_found": 404,
        "self_publication": 403,
        "already_decided": 409,
        "would_go_backwards": 409,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=str(exc))


async def _labelled(db, request, outs):
    """Render `producedBy`/`publishedBy` as emails instead of JWT subject UUIDs.

    Same reasoning as the Documents list — see `shared.services.actor_labels`. The
    version panel sat right beside that list showing the identical unreadable id.
    Accepts one VersionOut or a list; returns what it was given.
    """
    one = not isinstance(outs, list)
    items = [outs] if one else outs
    labels = await actor_labels(
        db, getattr(request.state, "tenant_id", None),
        [o.producedBy for o in items] + [o.publishedBy for o in items],
    )
    if labels:
        for o in items:
            o.producedBy = relabel(o.producedBy, labels) or o.producedBy
            o.publishedBy = relabel(o.publishedBy, labels)
    return items[0] if one else items


@artifact_versions_router.get(
    "/{project_id}/stages/{stage}/versions",
    response_model=list[VersionOut],
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def list_stage_versions(
    project_id: str,
    stage: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Every version of one stage, newest first. Reading is `artifact:view` — seeing
    what exists is not approving it."""
    try:
        svc.assert_known_stage(stage)
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = await svc.list_versions(db, project_id, stage)
    return await _labelled(db, request, [VersionOut.of(r) for r in rows])


@artifact_versions_router.get(
    "/{project_id}/stages/{stage}/versions/published",
    response_model=Optional[VersionDetailOut],
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_published_version(
    project_id: str,
    stage: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """The version consumers will read once phase 3 lands, or null.

    NULL IS A REAL ANSWER — "no approved design exists yet" — and the caller must say
    so rather than falling back to the draft. A fallback would make the gate
    decorative, exactly as the tenant-wide credential fallback made "Needs a
    credential" decorative until it was removed.
    """
    row = await svc.latest_published(db, project_id, stage)
    return await _labelled(db, request, VersionDetailOut.of(row)) if row is not None else None


@artifact_versions_router.get(
    "/{project_id}/stages/{stage}/versions/{version}",
    response_model=VersionDetailOut,
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_stage_version(
    project_id: str,
    stage: str,
    version: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    row = await svc.get_version(db, project_id, stage, version)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
    return await _labelled(db, request, VersionDetailOut.of(row))


@artifact_versions_router.post(
    "/{project_id}/stages/{stage}/versions",
    response_model=VersionOut,
    dependencies=[Depends(require_permission("run:create"))],
)
async def snapshot_stage_version(
    project_id: str,
    stage: str,
    body: SnapshotBody,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Freeze the stage's current working payload as the next version.

    `run:create` rather than the approve permission: taking a snapshot is producing
    work, not accepting it. The person doing it becomes `produced_by`, which is half
    of the self-publication check — so this cannot be done by an unidentified caller.
    """
    produced_by = getattr(request.state, "user_id", None)
    if not produced_by:
        raise HTTPException(
            status_code=403,
            detail="a version must record who produced it; this request has no user",
        )

    # THE PAYLOAD IS READ SERVER-SIDE when the caller does not send one, which is what
    # the UI does. A freeze captures what the AGENT produced; taking it from the
    # browser would let somebody freeze and publish something the agent never wrote,
    # with the gate wrapped approvingly around it. The body still accepts a payload for
    # programmatic callers that genuinely have one.
    payload = body.payload
    if payload is None:
        payload = await svc.current_working_payload(db, project_id, stage)
        if payload is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{stage} has produced nothing to freeze yet. Run the agent first — "
                    "a version has to capture something."
                ),
            )
    try:
        ref = await svc.snapshot_stage_payload(
            db, tenant_id=request.state.tenant_id, project_id=project_id, stage=stage,
            payload=payload, produced_by=produced_by, run_id=body.runId,
            covers=body.covers,
        )
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except svc.ArtifactVersionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await svc.get_version(db, project_id, stage, ref.version)
    return await _labelled(db, request, VersionOut.of(row))


class PublishBody(BaseModel):
    """Optional. A Project Admin approving a Track 3 version as FALLBACK must say why."""
    fallbackReason: Optional[str] = Field(default=None, max_length=2000)


@artifact_versions_router.post(
    "/{project_id}/stages/{stage}/versions/{version}/publish",
    response_model=VersionOut,
    dependencies=[Depends(require_stage_approval())],
)
async def publish_stage_version(
    project_id: str,
    stage: str,
    version: int,
    request: Request,
    body: Optional[PublishBody] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Sign a version off, as the role that owns this stage.

    The permission is resolved from the path's stage, so an Architect can publish a
    design and not a deployment. Self-publication is refused here and by the schema.

    TRACK 3 STAGES also record the approver's CAPACITY (`shared/services/fallback_approval`):
    the owning role, or a Project Admin of this project as labelled fallback with a reason.
    A refusal says why, in words (R14). Track 1 stages are unchanged.
    """
    actor = getattr(request.state, "user_id", None)
    if not actor:
        raise HTTPException(status_code=403, detail="Forbidden")
    capacity = None
    from shared.services import fallback_approval  # noqa: PLC0415

    if stage in fallback_approval.TRACK3_STAGES:
        from shared.services.version_lineage import producers_of  # noqa: PLC0415

        target = await svc.get_version(db, project_id, stage, version)
        if target is None:
            raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
        if target.status == "published":
            # Already decided: answer as before (a double-click is not an error) but NEVER
            # rewrite who approved it in which capacity — that record is the decision.
            return await _labelled(db, request, VersionOut.of(target))
        try:
            capacity = await fallback_approval.approval_capacity(
                db, tenant_id=str(request.state.tenant_id), project_id=project_id, stage=stage,
                user_id=str(actor), produced_by=target.produced_by, version_created_at=target.created_at,
                reason=body.fallbackReason if body else None,
                also_produced_by=await producers_of(db, project_id, stage, version),
            )
        except fallback_approval.ApprovalRefused as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        row = await svc.publish_version(
            db, tenant_id=request.state.tenant_id, project_id=project_id,
            stage=stage, version=version, published_by=actor,
        )
    except svc.PublicationRefused as exc:
        raise _refusal(exc) from exc
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if capacity is not None:
        row.approved_as, row.fallback_reason = capacity.approved_as, capacity.reason
        await db.flush()
    if stage == "design_modernization":
        await _design_approved(db, request, project_id, row)
    elif stage == "strategy":
        await _strategy_approved(db, request, project_id, row)
    elif stage == "testing_modernization" and (row.payload or {}).get("mode") == "verify":
        await _verification_approved(db, request, project_id, row)
    elif stage == "testing_modernization":
        await _baseline_approved(db, request, project_id, row)
    elif stage in ("code_review_modernization", "security_modernization"):
        await _verdict_approved(db, request, project_id, stage, row)
    return await _labelled(db, request, VersionOut.of(row))


async def _verdict_approved(db: AsyncSession, request: Request, project_id: str, stage: str, row) -> None:
    """Migration Review's and Security's ledger verdicts on ACCEPTANCE (Phase I, I11), in this request's
    transaction — a ledger refusal rolls the acceptance back. Only a review of the module's CURRENT
    migration counts: one made on an earlier record (the module was reworked since) is refused, so a
    stale approval can never move a reworked module on."""
    from shared.services import artifact_versions as versions  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    payload = row.payload or {}
    module_id = payload.get("module_id")
    review = stage == "code_review_modernization"
    verdict = payload.get("merge_recommendation" if review else "verdict")
    noun = "review" if review else "security report"
    if not module_id or not verdict or not payload.get("migration_version"):
        raise HTTPException(status_code=409, detail=(
            f"Not accepted: this {noun} names no module, verdict and migration; submit it with the agent."))
    current = next((r for r in await versions.list_versions(db, project_id, "development_modernization")
                    if (r.payload or {}).get("module_id") == module_id), None)
    if current is None or current.version != payload["migration_version"] \
            or (current.payload or {}).get("head_sha") != payload.get("head_sha"):
        raise HTTPException(status_code=409, detail=(
            f"Not accepted: this {noun} is of {module_id}'s migration record v{payload['migration_version']}, and the "
            f"module has been migrated again since (v{getattr(current, 'version', '?')}). Review the current one."))
    record = ledger.review_submitted if review else ledger.security_submitted
    try:
        await record(db, project_id=project_id, module_id=module_id, verdict=str(verdict),
                     actor=str(getattr(request.state, "user_id", "") or ""),
                     artifact=ledger.ArtifactRef("migration_review_artifacts" if review
                                                 else "modernization_security_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=f"Not accepted: {exc}") from exc


async def _verification_approved(db: AsyncSession, request: Request, project_id: str, row) -> None:
    """Equivalence Testing's Verify-mode ledger transition on ACCEPTANCE (Phase J, J8), in this request's
    transaction: `verifying → verified` (every criterion passed), back to `migrating` (a failure), or stays
    `verifying` (open). A verification of an older migration record than the module's current one is refused."""
    from shared.services import artifact_versions as versions  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    payload = row.payload or {}
    module_id, verdict = payload.get("module_id"), payload.get("module_verdict")
    if not module_id or verdict not in ("verified", "migrating", "open"):
        raise HTTPException(status_code=409, detail="Not accepted: this verification names no module and verdict.")
    current = next((r for r in await versions.list_versions(db, project_id, "development_modernization")
                    if (r.payload or {}).get("module_id") == module_id), None)
    if current is None or current.version != payload.get("migration_version") \
            or (current.payload or {}).get("head_sha") != payload.get("head_sha"):
        raise HTTPException(status_code=409, detail=(
            f"Not accepted: this verification is of {module_id}'s migration record v{payload.get('migration_version')}, "
            f"and the module has been migrated again since (v{getattr(current, 'version', '?')}). Verify the current one."))
    perf = payload.get("performance") or []
    perf_verdict = None
    if perf:
        measured = [p for p in perf if p.get("target_p95_ms") is not None]
        perf_verdict = ("not_measured" if len(measured) < len(perf) else
                        "passed" if all(p["target_p95_ms"] <= p["threshold_ms"] for p in measured) else "failed")
    try:
        await ledger.equivalence_recorded(
            db, project_id=project_id, module_id=module_id, verdict=verdict, perf_verdict=perf_verdict,
            actor=str(getattr(request.state, "user_id", "") or ""),
            artifact=ledger.ArtifactRef("equivalence_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=f"Not accepted: {exc}") from exc


async def _baseline_approved(db: AsyncSession, request: Request, project_id: str, row) -> None:
    """Equivalence Testing's ledger transition on ACCEPTANCE (Phase G): every baselined module
    `sequenced → baselined` with its BL ids, in this request's transaction — a ledger refusal rolls
    the acceptance back. The placements are the record tool's; a baseline without them marks no
    module and was not recorded by the agent."""
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    placements = (row.payload or {}).get("placements")
    if not placements:
        raise HTTPException(status_code=409, detail=(
            "Not accepted: this baseline marks no module on the ledger. Record it with the Equivalence Testing "
            "agent, mapping each module's criteria."))
    try:
        await ledger.baselines_approved(
            db, project_id=project_id, placements=placements,
            actor=str(getattr(request.state, "user_id", "") or ""),
            artifact=ledger.ArtifactRef("equivalence_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=f"Not accepted: {exc}") from exc


async def _strategy_approved(db: AsyncSession, request: Request, project_id: str, row) -> None:
    """Migration Strategy's ledger transition on APPROVAL (Phase F): every planned module
    `designed → sequenced` with its wave and criteria, in this request's transaction — a ledger
    refusal rolls the approval back. The placements are the record tool's, computed from the
    plan when it was checked; a plan without them was not recorded by the agent."""
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    placements = (row.payload or {}).get("placements")
    if not placements:
        raise HTTPException(status_code=409, detail=(
            "Not approved: this plan does not place its modules in waves the ledger can apply. Record the plan "
            "with the Migration Strategy agent."))
    try:
        await ledger.strategy_approved(
            db, project_id=project_id, placements=placements,
            actor=str(getattr(request.state, "user_id", "") or ""),
            artifact=ledger.ArtifactRef("strategy_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=f"Not approved: {exc}") from exc


async def _design_approved(db: AsyncSession, request: Request, project_id: str, row) -> None:
    """Target Architecture's ledger transition, wired to the version's APPROVAL (Phase E): every
    designed module enters the Module Migration Ledger as `designed`, in THIS request's
    transaction — so a ledger refusal (id drift, a trigger) rolls the approval back too, and an
    approved design never leaves the ledger behind it. Recording a design writes nothing here."""
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    payload = row.payload or {}
    paths = payload.get("module_paths") or {}
    modules = [{
        "module_id": m.get("module_id"), "module_name": m.get("module"),
        "legacy_path": paths.get(m.get("module_id")) or "", "tier": m.get("tier"),
        "risk_score": m.get("risk_score"), "patterns": m.get("patterns") or [],
        "contract_ids": m.get("contract_ids") or [], "adr_ids": m.get("adr_ids") or [],
    } for m in payload.get("modules") or [] if m.get("module_id")]
    # A design the agent recorded carries every module's legacy path (from the pinned assessment).
    # One without them (a payload snapshotted by another caller) cannot be checked for id drift,
    # so it does not reach the ledger (review fix #8).
    unplaced = [m["module_id"] for m in modules if not m["legacy_path"]]
    if unplaced:
        raise HTTPException(status_code=409, detail=(
            f"Not approved: this design does not say where {', '.join(unplaced)} live in the legacy code, so the "
            "ledger cannot check its module ids. Record the design with the Target Architecture agent."))
    try:
        await ledger.design_approved(
            db, tenant_id=str(request.state.tenant_id), project_id=project_id, modules=modules,
            actor=str(getattr(request.state, "user_id", "") or ""),
            artifact=ledger.ArtifactRef("target_design_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        raise HTTPException(status_code=409, detail=f"Not approved: {exc}") from exc


@artifact_versions_router.post(
    "/{project_id}/stages/{stage}/versions/{version}/reject",
    response_model=VersionOut,
    dependencies=[Depends(require_stage_approval())],
)
async def reject_stage_version(
    project_id: str,
    stage: str,
    version: int,
    body: RejectBody,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Refuse a version, with a reason. The row stays readable — a rejection is a
    decision, not a deletion.

    TRACK 3 STAGES: the permission is a tenant-wide union, so it alone would let a BA of
    another project reject this one's brief. The rejecter must be the owning role or a
    Project Admin ON THIS PROJECT. (The producer is refused by the service either way —
    whoever produced a version decides it neither way.)"""
    actor = getattr(request.state, "user_id", None)
    if not actor:
        raise HTTPException(status_code=403, detail="Forbidden")
    from shared.services import fallback_approval  # noqa: PLC0415

    if stage in fallback_approval.TRACK3_STAGES:
        target = await svc.get_version(db, project_id, stage, version)
        if target is None:
            raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
        roles = await fallback_approval.project_roles(
            db, tenant_id=str(request.state.tenant_id), project_id=project_id, user_id=str(actor))
        owner = fallback_approval.agent_owner_role(stage)
        if owner not in roles and "project_admin" not in roles:
            raise HTTPException(status_code=403, detail=(
                f"only a {owner.replace('_', ' ')} or a Project Admin of this project rejects this"))
    try:
        row = await svc.reject_version(
            db, tenant_id=request.state.tenant_id, project_id=project_id,
            stage=stage, version=version, rejected_by=actor, reason=body.reason,
        )
    except svc.PublicationRefused as exc:
        raise _refusal(exc) from exc
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _labelled(db, request, VersionOut.of(row))


@artifact_versions_router.post(
    "/{project_id}/stages/{stage}/versions/{version}/request-access",
    dependencies=[Depends(require_permission("run:create"))],
)
async def request_consumption_access(
    project_id: str,
    stage: str,
    version: int,
    body: ConsumptionRequestBody,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Ask the producing stage's owner to allow a version the gate refuses.

    THE ONLY WAY PAST THE GATE, and it goes to a named human rather than a flag. Three
    situations reach here — an unpublished draft, a superseded version somebody wants
    to pin, and (once cross-project reads exist) another team's work.

    `run:create`, not the approve permission: ASKING is not deciding. The approver is
    `agent_owner_role(stage)` — the role that signs this stage off — set by
    `create_request`, and the existing self-approval rules apply to their decision.

    Everything else — the normal path, a published version — needs no request at all.
    Requiring one per consumer per artifact is up to seventy-two pairs per project,
    rubber-stamped inside a week.
    """
    actor = getattr(request.state, "user_id", None)
    if not actor:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        svc.assert_known_stage(stage)
        svc.assert_known_stage(body.consumerStage)
    except svc.UnknownStage as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    row = await svc.get_version(db, project_id, stage, version)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
    if row.status == "published":
        # Nothing to ask for. Filing a request that grants what the caller already has
        # trains an approver that these are noise.
        raise HTTPException(
            status_code=409,
            detail=f"{stage} v{version} is already published; no request is needed.",
        )

    from shared.services import governance_requests as gov  # noqa: PLC0415

    project = getattr(request.state, "project", None)
    result = await gov.create_request(
        db,
        tenant_id=request.state.tenant_id,
        initiator_id=actor,
        initiator_name=actor,
        initiator_role=getattr(request.state, "role", None),
        request_type="artifact_consumption",
        title=f"{body.consumerStage} needs {stage} v{version} ({row.status})",
        description=body.reason,
        workspace_id=str(getattr(project, "workspace_id", "") or ""),
        project_id=project_id,
        # Routes the approver to this stage's owner — see create_request.
        phase=stage,
        payload={
            "versionId": str(row.id),
            "consumerStage": body.consumerStage,
            "projectId": project_id,
            "versionStatus": row.status,
            "contentHash": row.content_hash,
        },
        system_raised=True,
    )
    return {"requestId": result.get("id"), "approverRole": result.get("currentApproverRole")}


@artifact_versions_router.get(
    "/{project_id}/matrix",
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_consumption_matrix(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Who may read whose artifacts on this project.

    `artifact:view`, not an approve permission: SEEING the rules is not deciding
    anything, and a matrix only the approvers can read would leave everyone else
    discovering the rules by being refused.

    `enforced` is part of the answer, not context. With it false every cell is
    academic — agents still read the working draft — and a matrix that did not say so
    would be describing a gate that is not switched on.
    """
    return {
        "enforced": await svc.enforcement_enabled(db, project_id),
        "stages": await svc.consumption_matrix(db, project_id),
    }


@artifact_versions_router.get(
    "/{project_id}/runs/{run_id}/evidence",
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_run_evidence(
    project_id: str,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """What this run built on, with the content hash of each thing it read.

    THE QUESTION AN AUDITOR ASKS, and before phase 3 it had no answer at all — every
    consumer took the latest non-null payload, so nothing recorded that a particular
    run read a particular thing. Not a stale answer: none.

    An EMPTY LIST is meaningful and not an error. It means the run consumed nothing
    through the gate — either it had no upstream, or the project was not enforcing
    publication when it ran, in which case there is genuinely no record to show. The
    UI has to say which rather than rendering blank.
    """
    return {"runId": run_id, "consumed": await svc.run_evidence(db, run_id)}


@artifact_versions_router.get(
    "/{project_id}/stages/{stage}/versions/{version}/consumers",
    dependencies=[Depends(require_permission("artifact:view"))],
)
async def get_version_consumers(
    project_id: str,
    stage: str,
    version: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """What was built on this version — the blast radius of one signed artifact.

    The question asked after a design turns out to be wrong: everything downstream
    that has to be looked at again.
    """
    row = await svc.get_version(db, project_id, stage, version)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{stage} v{version} not found")
    return {
        "stage": stage,
        "version": version,
        "status": row.status,
        "contentHash": row.content_hash,
        "consumers": await svc.version_consumers(db, project_id, stage, version),
    }
