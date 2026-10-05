"""Tools of the Migration Review agent (Track 3, Phase I).

  read      the ledger; the module's ACCEPTED migration with its design and plan slice; both sides of the
            module, paired through the file map (`modernization_common/review_tools`). Every file opened
            is noted: the review can only cite what it opened.
  compute   `compare_api_surface` and `detect_legacy_antipatterns` — deterministic, on the head that was
            accepted and the legacy commit pulled (`analysis`).
  submit    `submit_migration_review` — the packet's own merge rules, then completeness, honesty and the
            diff (`checks`); frozen as the next version (one version = one module's review). The ledger
            verdict is written when the Architect ACCEPTS the version, not here.

Read-only on both repositories. Submitting runs on the Migration Review page only (an Orchestrator
conversation can explain, not review).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from agents_orchestrator.code_review_modernization_agent import analysis as A
from agents_orchestrator.modernization_common import review_checkout as RC
from agents_orchestrator.modernization_common.review_tools import make_review_read_tools, module_context

logger = logging.getLogger(__name__)

STAGE = "code_review_modernization"
LABEL = "Migration Review"
FILE_SEGMENT = "code_review_modernization_agent"
REVIEW_ROLES = {"architect", "project_admin"}


def _scope() -> tuple[str, str, str]:
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    return str(get_tenant_id() or ""), str(get_project_id() or ""), str(get_user_id() or "")


def _page_only() -> Optional[str]:
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run():
        return ("Reviews are submitted on the Migration Review page, against the module's ACCEPTED migration. Open the "
                "page to review; here I can explain.")
    return None


async def _roles() -> set[str]:
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services.fallback_approval import project_roles  # noqa: PLC0415

    tenant, project, user = _scope()
    try:
        async with get_db_session_for_tenant(tenant) as db:
            return await project_roles(db, tenant_id=tenant, project_id=project, user_id=user)
    except Exception:  # noqa: BLE001 — cannot prove the role ⇒ none
        return set()


async def _may_review() -> Optional[str]:
    if not (await _roles()) & REVIEW_ROLES:
        return "Only an Architect or a Project Admin of this project submits a migration review. Ask one of them."
    return None


async def _audit(event_type: str, module_id: str, payload: dict) -> None:
    from shared.audit.models import AuditEventPayload  # noqa: PLC0415
    from shared.audit.service import audit_service  # noqa: PLC0415

    tenant, project, user = _scope()
    if tenant:
        await audit_service.emit(AuditEventPayload(
            tenant_id=tenant, event_type=event_type, agent_type=STAGE, actor_id=user or None,
            resource_type="project", resource_id=project or None, payload={"moduleId": module_id, **payload}))


def compute(mig: RC.Migration, ctx: dict) -> tuple[dict, dict]:
    """(surface diff, anti-pattern classification) on the two sides. Pure apart from reading files."""
    legacy_files, target_files = mig.legacy_module_files(), mig.target_paths()
    legacy = A.surface(mig.legacy, mig.module_path, legacy_files)
    target = A.surface(mig.target, mig.module_path, target_files)
    diff = A.compare_surfaces(legacy, target, file_map=mig.record.get("file_map") or [], contracts=ctx["contracts"])
    hits = A.classify(A.antipatterns(A.module_texts(mig.legacy, legacy_files)),
                      A.antipatterns(A.module_texts(mig.target, target_files)), mig.record.get("file_map") or [])
    return diff, hits


async def _both(module_id: str) -> tuple[Optional[RC.Migration], Optional[dict], str]:
    ctx, why = await module_context(module_id)
    if ctx is None:
        return None, None, why
    mig, why = await RC.open_migration(STAGE, module_id, LABEL)
    if mig is None:
        return None, None, why
    if mig.legacy is None:
        return None, None, "The legacy code is not pulled for this stage: pull it first (the review is side by side)."
    return mig, ctx, ""


@tool
async def compare_api_surface(module_id: str) -> str:
    """Diff what the legacy module and the migrated module expose and depend on — routes, HTTP methods and
    status codes, public functions, SQL statements, file formats and encodings — and which frozen contract
    each difference touches. Deterministic."""
    import asyncio  # noqa: PLC0415

    mig, ctx, why = await _both(module_id)
    if mig is None:
        return why
    diff, _hits = await asyncio.to_thread(compute, mig, ctx)
    return A.surface_markdown(diff, module_id)


@tool
async def detect_legacy_antipatterns(module_id: str) -> str:
    """Scan both sides with the legacy anti-pattern rule pack (string-built SQL, swallowed exceptions, Python 2
    idioms, hard-coded hosts and credentials, static mutable state, Log4j 1, SimpleDateFormat, AngularJS) and
    mark each target hit carried over or introduced, and each legacy-only hit fixed. Leads, not findings."""
    import asyncio  # noqa: PLC0415

    mig, ctx, why = await _both(module_id)
    if mig is None:
        return why
    _diff, hits = await asyncio.to_thread(compute, mig, ctx)
    return A.antipatterns_markdown(hits, module_id)


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the module's current migration review."
    except Exception as exc:  # noqa: BLE001
        logger.exception("migration review: persisting the review failed")
        return f"Not saved ({type(exc).__name__}) — the review below is still complete."


def build_artifact(*, module_id: str, review: dict, mig: RC.Migration, ctx: dict, opened: dict, diff: dict, hits: dict,
                   recorded_at: Optional[str], session: str = "") -> dict:
    """The stored review (`MigrationReviewArtifact`) — ONE builder, for the submit tool and the view fixtures."""
    from shared.models.artifacts import MigrationReviewArtifact  # noqa: PLC0415

    pr = mig.record.get("pr_url") or mig.ledger.get("prUrl") or f"{mig.branch}@{mig.head[:10]}"
    return MigrationReviewArtifact(
        module_id=module_id, pr=pr, summary=review.get("summary") or "",
        merge_recommendation=review.get("merge_recommendation") or "",
        findings=list(review.get("findings") or []), equivalence_coverage=list(review.get("equivalence_coverage") or []),
        contract_check=list(review.get("contract_check") or []), trap_check=list(review.get("trap_check") or []),
        traceability=list(review.get("traceability") or []), known_debt=list(review.get("known_debt") or []),
        files_read={"target": sorted(opened.get("target") or []), "legacy": sorted(opened.get("legacy") or [])},
        migration_version=mig.version, head_sha=mig.head, legacy_commit=mig.legacy_commit,
        module={"name": ctx.get("name"), "tier": ctx.get("tier"), "patterns": ctx.get("patterns"),
                "legacy_path": mig.module_path, "contract_ids": [c["id"] for c in ctx["contracts"]],
                "trap_ids": [t["id"] for t in ctx["traps"]], "criterion_ids": [c["id"] for c in ctx["criteria"]]},
        sources={**ctx["sources"], "migration": {"version": mig.version, "status": mig.status}},
        surface={"removed": diff["removed"][:200], "added": diff["added"][:200],
                 "contracts": {k: v[:50] for k, v in diff["contracts"].items()},
                 "legacy_count": diff["legacy_count"], "target_count": diff["target_count"]},
        antipatterns={"target": hits["target"][:300], "fixed": hits["fixed"][:300]},
        system_name=ctx.get("system_name") or "", recorded_at=recorded_at, agent_session_id=session or None,
    ).model_dump(mode="json")


@tool
async def submit_migration_review(module_id: str, summary: str, merge_recommendation: str,
                                  findings: Optional[list] = None, equivalence_coverage: Optional[list] = None,
                                  contract_check: Optional[list] = None, trap_check: Optional[list] = None,
                                  traceability: Optional[list] = None, known_debt: Optional[list] = None) -> str:
    """Submit the module's migration review, once, as the next version (one version = one module).

    Args:
        summary: markdown — what changed, the risk, the key findings.
        merge_recommendation: approve | request_changes | needs_discussion.
        findings: [{"id": "F-001", "severity": critical|high|medium|low|info, "category": contract_drift|
            trap_unhandled|behaviour_change|carried_over|introduced|scope_creep|traceability|design|maintainability|
            style, "file": target path, "line", "legacy_file", "legacy_line", "description", "recommendation",
            "refs": ["CT-01", "TR-02", "EC-04", "ADR-03"], "autofix_patch"}].
        equivalence_coverage: EVERY criterion of the module: [{"ec_id", "status": covered|at_risk|not_addressed, "note"}].
        contract_check: EVERY frozen contract: [{"ct_id", "status": unchanged|changed_allowed|changed, "note"}].
        trap_check: EVERY trap: [{"tr_id", "status": handled|not_handled|not_applicable, "where": "file:line"}].
        traceability: EVERY legacy file: [{"legacy_path", "target_path", "status": mapped|merged|dropped_justified|missing}].
        known_debt: carried-over issues kept on purpose: [{"pattern", "legacy_file", "note"}].
    The pull request, the head reviewed and the files read are taken from the tools — not from you."""
    import asyncio  # noqa: PLC0415

    from agents_orchestrator.code_review_modernization_agent.checks import check  # noqa: PLC0415
    from agents_orchestrator.code_review_modernization_agent.review_document import review_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.handover.emit import review_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from config.ws_helper import get_session_id  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_review()):
        return why
    mig, ctx, why = await _both(module_id)
    if mig is None:
        return why
    if mig.ledger.get("state") != "in_review":
        return (f"{module_id} is {mig.ledger.get('state')}; a review is submitted while the module is in review (its pull "
                "request opened by Migration Development).")
    diff, hits = await asyncio.to_thread(compute, mig, ctx)
    opened = RC.files_opened(STAGE, module_id)
    review = {"summary": summary, "merge_recommendation": merge_recommendation, "findings": findings or [],
              "equivalence_coverage": equivalence_coverage or [], "contract_check": contract_check or [],
              "trap_check": trap_check or [], "traceability": traceability or [], "known_debt": known_debt or []}
    try:
        artifact = build_artifact(module_id=module_id, review=review, mig=mig, ctx=ctx, opened=opened, diff=diff, hits=hits,
                                  recorded_at=datetime.now(timezone.utc).isoformat(), session=str(get_session_id() or ""))
    except Exception as exc:  # noqa: BLE001 — a malformed argument the model sent
        return f"NOT SUBMITTED — the review could not be built: {type(exc).__name__}: {str(exc)[:300]}"
    handover = review_packet(artifact, {"version": 1, "status": "draft"})
    problems = list(handover.problems)
    if handover.ok:
        problems += check(review=artifact, ctx=ctx, record=mig.record, opened=opened, surface=diff,
                          legacy_files=mig.legacy_module_files())
    if problems:
        return "NOT SUBMITTED — " + "\n".join(f"- {p}" for p in problems[:16])
    saved = await _persist(artifact)
    version = await freeze_version(STAGE, artifact)
    await _audit("modernization.review_submitted", module_id,
                 {"recommendation": merge_recommendation, "head": mig.head, "version": version})
    return (f"{review_markdown(artifact)}\n\n_{saved_line(saved, version, 'migration review')}_\n\n"
            "The Architect accepts it on the Migration Review page; accepting records the recommendation on the ledger.")


@tool
async def export_review_document(module_id: str, filename: str = "migration-review.docx") -> str:
    """Export a module's newest migration review as a document (.docx, .pdf or .md)."""
    import os  # noqa: PLC0415

    from agents_orchestrator.code_review_modernization_agent.review_document import review_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415
    from shared.tools.doc_export import export_result_message, normalise_filename, render_document, supported_list  # noqa: PLC0415

    tenant, project, _u = _scope()
    row = None
    async with get_db_session_for_tenant(tenant) as db:
        for r in await svc.list_versions(db, project, STAGE):
            if (r.payload or {}).get("module_id") == module_id:
                row = r
                break
    if row is None or not row.payload:
        return f"{module_id} has no migration review yet."
    name = normalise_filename(filename, "migration-review.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(review_markdown(row.payload), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(name, url, ["The review VERSION on the page is what gets accepted."])


def _ledger_tool():
    from agents_orchestrator.development_modernization_agent.tools.migration_tools import get_ledger  # noqa: PLC0415

    return get_ledger


READ_TOOLS = make_review_read_tools(STAGE, LABEL)
TOOLS = [_ledger_tool(), *READ_TOOLS, compare_api_surface, detect_legacy_antipatterns, submit_migration_review,
         export_review_document]
