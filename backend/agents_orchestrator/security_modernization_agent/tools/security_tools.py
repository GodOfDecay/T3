"""Tools of the Security (Modernization) agent (Track 3, Phase I).

  read      the ledger; the module's ACCEPTED migration and both sides (`modernization_common/review_tools`).
  scan      `scan_migrated_module` (the target at the accepted head) and `scan_legacy_baseline` (the legacy
            module, cached per legacy commit): Trivy, Semgrep, Gitleaks in pinned, offline containers
            (`scanners`). Results are kept beside the review checkout; secret VALUES never are.
  compare   `diff_findings`, `check_secret_carryover`, `check_contract_authz` — deterministic (`compare`).
  submit    `submit_security_report` — scans, SBOM, scanner hits and fixed-from-legacy from the tools; the
            policy verdict from the packet; nothing left out (`checks`). Frozen as the next version. The
            ledger verdict is written when the Security Engineer ACCEPTS the version.

Read-only on both repositories. Submitting runs on the Security page only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from agents_orchestrator.modernization_common import review_checkout as RC
from agents_orchestrator.modernization_common.review_tools import make_review_read_tools, module_context
from agents_orchestrator.security_modernization_agent import compare as C
from agents_orchestrator.security_modernization_agent import scanners as S

logger = logging.getLogger(__name__)

STAGE = "security_modernization"
LABEL = "Security (Modernization)"
FILE_SEGMENT = "security_modernization_agent"
SECURITY_ROLES = {"security_engineer", "project_admin"}
_SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _scope() -> tuple[str, str, str]:
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    return str(get_tenant_id() or ""), str(get_project_id() or ""), str(get_user_id() or "")


def _page_only() -> Optional[str]:
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run():
        return ("Security reports are submitted on the Security page, against the module's ACCEPTED migration. Open the "
                "page to scan; here I can explain.")
    return None


async def _may_sign() -> Optional[str]:
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services.fallback_approval import project_roles  # noqa: PLC0415

    tenant, project, user = _scope()
    try:
        async with get_db_session_for_tenant(tenant) as db:
            roles = await project_roles(db, tenant_id=tenant, project_id=project, user_id=user)
    except Exception:  # noqa: BLE001 — cannot prove the role ⇒ none
        roles = set()
    if not roles & SECURITY_ROLES:
        return "Only a Security Engineer or a Project Admin of this project scans and submits a security report."
    return None


async def _audit(event_type: str, module_id: str, payload: dict) -> None:
    from shared.audit.models import AuditEventPayload  # noqa: PLC0415
    from shared.audit.service import audit_service  # noqa: PLC0415

    tenant, project, user = _scope()
    if tenant:
        await audit_service.emit(AuditEventPayload(
            tenant_id=tenant, event_type=event_type, agent_type=STAGE, actor_id=user or None,
            resource_type="project", resource_id=project or None, payload={"moduleId": module_id, **payload}))


# ── state (beside the checkout; never a secret value) ──────────────────────

def _state_path(mig: RC.Migration) -> pathlib.Path:
    _t, project, _u = _scope()
    return RC.checkout_dir(project, STAGE, mig.module_id, mig.head) / "security.json"


def _legacy_path(mig: RC.Migration) -> pathlib.Path:
    _t, project, _u = _scope()
    commit = "".join(c for c in (mig.legacy_commit or "unknown") if c.isalnum())[:40] or "unknown"
    return RC.checkout_dir(project, STAGE, mig.module_id, mig.head).parent / f"legacy-{commit}.json"


def read_json(path: pathlib.Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _public(result: dict) -> dict:
    """A scan result without the secret values."""
    return {k: v for k, v in result.items() if k != "secret_values"} | {"at": datetime.now(timezone.utc).isoformat()}


def _not_run(why: str) -> dict:
    return {"scans": {t: "not_installed" for t in S.SCANNERS}, "notes": {t: why for t in S.SCANNERS}, "findings": [],
            "sbom": {"components": None, "vulnerabilities": None}, "versions": dict(S.VERSIONS)}


def _scan_markdown(title: str, result: dict, cached: bool = False) -> str:
    sb = result.get("sbom") or {}
    lines = [f"# {title}" + (" (from the cache for this legacy commit)" if cached else ""), "",
             "| Scanner | Status | Note |", "|---|---|---|"]
    lines += [f"| {t} {S.VERSIONS.get(t, '')} | {result['scans'].get(t, 'not_run').replace('_', ' ')} | "
              f"{(result.get('notes') or {}).get(t, '')[:160]} |" for t in S.SCANNERS]
    comps = sb.get("components")
    vulns = sb.get("vulnerabilities")
    lines.append(f"\nSBOM: {'not generated' if comps is None else f'{comps} components'}; dependency vulnerabilities: "
                 f"{'not scanned' if vulns is None else vulns}.")
    fs = sorted(result.get("findings") or [], key=lambda f: (_SEV.get(f["severity"], 9), f.get("file") or ""))
    if fs:
        lines += ["", "| Severity | Scanner | What | Where |", "|---|---|---|---|"]
        lines += [f"| {f['severity']} | {f['tool']} | {(f.get('cve') + ' ' + (f.get('package') or '') + '@' + (f.get('version') or '')) if f.get('cve') else f['title'][:80]} | "
                  f"{f.get('file') or ''}{(':' + str(f['line'])) if f.get('line') else ''} |" for f in fs[:80]]
    elif all(result["scans"].get(t) == "ran" for t in S.SCANNERS):
        lines.append("\nNo findings from the three scanners.")
    return "\n".join(lines)


async def _migration(module_id: str, clone: bool = True) -> tuple[Optional[RC.Migration], str]:
    mig, why = await RC.open_migration(STAGE, module_id, LABEL, clone=clone)
    return mig, why


def _scan(base: pathlib.Path, module_path: str, label: str) -> dict:
    if why := S.available():
        return _not_run(why)
    try:
        return S.scan(base, module_path, label=label)
    except S.ScannerUnavailable as exc:
        return _not_run(str(exc))


@tool
async def scan_migrated_module(module_id: str) -> str:
    """Scan the migrated module on the target, at the head that was accepted: Trivy (dependency vulnerabilities
    and the SBOM), Semgrep (static analysis) and Gitleaks (secrets), pinned and offline."""
    if why := await _may_sign():
        return why
    mig, why = await _migration(module_id)
    if mig is None:
        return why
    result = await asyncio.to_thread(_scan, mig.target, mig.module_path, f"{module_id}-target")
    state = read_json(_state_path(mig)) or {}
    state["target"] = _public(result)
    write_json(_state_path(mig), state)
    return _scan_markdown(f"Scan of the migrated {module_id} at {mig.head[:10]}", state["target"])


@tool
async def scan_legacy_baseline(module_id: str) -> str:
    """Scan the LEGACY module with the same scanners (cached per legacy commit), for the comparison."""
    if why := await _may_sign():
        return why
    mig, why = await _migration(module_id, clone=False)
    if mig is None:
        return why
    if mig.legacy is None:
        return "The legacy code is not pulled for this stage: pull it first."
    cached = read_json(_legacy_path(mig))
    if cached and all(cached["scans"].get(t) == "ran" for t in S.SCANNERS):
        cached["served_from_cache"] = True
        write_json(_legacy_path(mig), cached)
        return _scan_markdown(f"Scan of the legacy {module_id} at {mig.legacy_commit[:10]}", cached, cached=True)
    result = await asyncio.to_thread(_scan, mig.legacy, mig.module_path, f"{module_id}-legacy")
    write_json(_legacy_path(mig), _public(result))
    return _scan_markdown(f"Scan of the legacy {module_id} at {mig.legacy_commit[:10]}", _public(result))


def diff_of(mig: RC.Migration) -> tuple[Optional[dict], str]:
    state = read_json(_state_path(mig)) or {}
    legacy = read_json(_legacy_path(mig))
    if not state.get("target"):
        return None, "Scan the migrated module first."
    if legacy is None:
        return None, "Scan the legacy module first (the comparison needs both)."
    return C.diff_findings(legacy["findings"], state["target"]["findings"], mig.record.get("file_map") or []), ""


@tool
async def diff_findings(module_id: str) -> str:
    """Compare the two scans: each target finding carried over or introduced, each legacy-only finding fixed."""
    mig, why = await _migration(module_id, clone=False)
    if mig is None:
        return why
    diff, why = diff_of(mig)
    if diff is None:
        return why
    t = sorted(diff["target"], key=lambda f: (_SEV.get(f["severity"], 9), f["origin"]))
    lines = [f"# {module_id}: {sum(1 for f in t if f['origin'] == 'introduced')} introduced, "
             f"{sum(1 for f in t if f['origin'] == 'carried_over')} carried over, {len(diff['fixed'])} fixed", ""]
    if t:
        lines += ["| Severity | Origin | What | Target | Legacy |", "|---|---|---|---|---|"]
        lines += [f"| {f['severity']} | {f['origin'].replace('_', ' ')} | {f.get('cve') or f['title'][:70]} "
                  f"{('(' + (f.get('package') or '') + ')') if f.get('package') else ''} | {f.get('file') or ''}"
                  f"{(':' + str(f['line'])) if f.get('line') else ''} | {f.get('legacy_ref') or '—'} |" for f in t[:80]]
    if diff["fixed"]:
        lines += ["", "Fixed by the migration:"] + [f"- {f.get('cve') or f['title'][:80]} ({f['legacy_ref']})" for f in diff["fixed"][:40]]
    return "\n".join(lines)


def carryover_of(mig: RC.Migration) -> list[dict]:
    """Legacy secret values (Gitleaks' and hard-coded credentials) found in the target. Values stay in memory."""
    from agents_orchestrator.code_review_modernization_agent.analysis import module_texts  # noqa: PLC0415

    legacy_texts = module_texts(mig.legacy, mig.legacy_module_files())
    values = [(v, f, n) for v, f, n in C.credential_values(legacy_texts)]
    if S.available() is None:  # Docker answers: Gitleaks' secrets too
        try:
            raw = S._run("gitleaks", mig.legacy, ["dir", f"/scan/{mig.module_path}", "-f", "json", "-r", "/dev/stdout",
                                                   "--no-banner", "--exit-code", "0"], [], f"{mig.module_id}-carryover")
            hits, secrets = S.parse_gitleaks(raw)
            values += [(s, h["file"], h["line"]) for s, h in zip(secrets, hits)]
        except (S.ScannerUnavailable, ValueError):
            logger.warning("security: gitleaks unavailable for the carry-over check; credential patterns only")
    target_texts = module_texts(mig.target, mig.target_paths())
    return C.secret_carryover(values, target_texts)


@tool
async def check_secret_carryover(module_id: str) -> str:
    """Look for every legacy secret value (by value, never shown) in the migrated code. Any hit is critical."""
    mig, why = await _migration(module_id)
    if mig is None:
        return why
    if mig.legacy is None:
        return "The legacy code is not pulled for this stage: pull it first."
    hits = await asyncio.to_thread(carryover_of, mig)
    state = read_json(_state_path(mig)) or {}
    state["carryover"] = hits
    write_json(_state_path(mig), state)
    if not hits:
        return "No legacy secret value appears in the migrated module (Gitleaks' secrets and hard-coded credentials checked)."
    return ("LEGACY SECRETS IN THE TARGET (critical, FAIL; rotate as well as remove):\n"
            + "\n".join(f"- {h['file']}:{h['line']} — the value from {h['legacy_file']}:{h['legacy_line']}" for h in hits))


def authz_of(mig: RC.Migration, ctx: dict) -> dict[str, dict]:
    to_target: dict[str, list[str]] = {}
    for e in mig.record.get("file_map") or []:
        if e.get("target_path"):
            to_target.setdefault(e["legacy_path"], []).append(e["target_path"])
    out = {}
    for c in ctx["contracts"]:
        if c.get("kind") != "http":
            continue
        legacy_file = str(c.get("legacy_location") or "").split(":", 1)[0].strip().lstrip("/")
        lp = RC.resolve(mig.legacy, legacy_file)
        targets = [RC.resolve(mig.target, t) for t in to_target.get(legacy_file, [legacy_file])]
        ltext = lp.read_text(encoding="utf-8", errors="replace") if lp else ""
        ttext = "\n".join(t.read_text(encoding="utf-8", errors="replace") for t in targets if t)
        ev = C.contract_authz(ltext, ttext)
        ev.update(legacy_file=legacy_file, target_files=[t for t in to_target.get(legacy_file, [legacy_file])],
                  found=bool(lp) and any(targets))
        out[c["id"]] = ev
    return out


@tool
async def check_contract_authz(module_id: str) -> str:
    """For every frozen HTTP contract of the module: the authentication and authorization markers on both sides
    (decorators, Authorization / API-key checks, role checks) and whether the target looks the same, stricter or weaker."""
    ctx, why = await module_context(module_id)
    if ctx is None:
        return why
    mig, why = await _migration(module_id)
    if mig is None:
        return why
    if mig.legacy is None:
        return "The legacy code is not pulled for this stage: pull it first."
    out = authz_of(mig, ctx)
    state = read_json(_state_path(mig)) or {}
    state["authz"] = out
    write_json(_state_path(mig), state)
    if not out:
        return f"{module_id} has no frozen HTTP contract: nothing to compare."
    lines = []
    for ct, ev in out.items():
        lines.append(f"- {ct} ({ev['legacy_file']} → {', '.join(ev['target_files'])}): looks **{ev['suggested']}** — {ev['reason']}."
                     + ("" if ev["found"] else " (a file could not be read: check by hand)"))
        for side in ("legacy", "target"):
            if ev[side]:
                lines.append(f"  {side}: " + ", ".join(f"{k} lines {', '.join(map(str, v[:5]))}" for k, v in ev[side].items()))
    return "\n".join(lines) + "\n\nRead the handlers before you state same, stricter or weaker."


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the module's current security report."
    except Exception as exc:  # noqa: BLE001
        logger.exception("security modernization: persisting the report failed")
        return f"Not saved ({type(exc).__name__}) — the report below is still complete."


def build_artifact(*, module_id: str, report: dict, mig: RC.Migration, ctx: dict, state: dict, legacy: dict,
                   diff: dict, recorded_at: Optional[str], session: str = "") -> dict:
    """The stored report (`ModernizationSecurityArtifact`) — ONE builder, for the submit tool and the view fixtures."""
    from agents_orchestrator.modernization_common.handover.packets import SecurityPayload  # noqa: PLC0415
    from shared.models.artifacts import ModernizationSecurityArtifact  # noqa: PLC0415

    target = state["target"]
    pr = mig.record.get("pr_url") or mig.ledger.get("prUrl") or f"{mig.branch}@{mig.head[:10]}"
    fixed = [{"title": f.get("title") or f.get("rule") or "", "cve": f.get("cve"), "package": f.get("package"),
              "legacy_ref": f["legacy_ref"]} for f in diff["fixed"]]
    artifact = ModernizationSecurityArtifact(
        module_id=module_id, pr=pr, legacy_commit=mig.legacy_commit or "not pulled",
        scans={t: target["scans"].get(t, "not_run") for t in S.SCANNERS},
        findings=list(report.get("findings") or []), fixed_from_legacy=fixed,
        contract_authz=list(report.get("contract_authz") or []), sbom=dict(target.get("sbom") or {}),
        verdict=report.get("verdict") or "", rationale=report.get("rationale") or "",
        migration_version=mig.version, head_sha=mig.head,
        module={"name": ctx.get("name"), "legacy_path": mig.module_path,
                "contract_ids": [c["id"] for c in ctx["contracts"]]},
        sources={**ctx["sources"], "migration": {"version": mig.version, "status": mig.status}},
        scanner_versions=dict(target.get("versions") or S.VERSIONS), scan_notes=dict(target.get("notes") or {}),
        target_hits=diff["target"][:400], legacy_hits=(legacy.get("findings") or [])[:400],
        legacy_cached=bool(legacy.get("served_from_cache")), secret_carryover=list(state.get("carryover") or []),
        authz_evidence=dict(state.get("authz") or {}),
        system_name=ctx.get("system_name") or "", recorded_at=recorded_at, agent_session_id=session or None,
    ).model_dump(mode="json")
    try:
        artifact["required_verdict"] = SecurityPayload.model_validate(
            {k: artifact[k] for k in SecurityPayload.model_fields if k in artifact} | {"verdict": "FAIL"}
        ).required_verdict()
    except Exception:  # noqa: BLE001 — the packet check reports the problem
        artifact["required_verdict"] = None
    return artifact


@tool
async def submit_security_report(module_id: str, verdict: str, rationale: str, findings: Optional[list] = None,
                                 contract_authz: Optional[list] = None) -> str:
    """Submit the module's security report, once, as the next version (one version = one module).

    Args:
        verdict: FAIL | CONDITIONAL | PASS — the Track 3 policy decides; a stated verdict that disagrees is refused.
        rationale: why, in a few sentences.
        findings: [{"id": "S-001", "title", "severity", "origin": carried_over|introduced, "legacy_ref", "reachable":
            true|false|null, "is_secret", "cve", "package", "file", "remediation_plan", "remediation_due": "YYYY-MM-DD"}] —
            every critical/high scanner hit on the target, and every carried-over secret.
        contract_authz: every frozen HTTP contract: [{"ct_id", "status": same|stricter|weaker, "note"}].
    The scans, the SBOM, the scanner hits and the findings fixed from the legacy are taken from the tools."""
    from agents_orchestrator.modernization_common.handover.emit import security_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from agents_orchestrator.security_modernization_agent.checks import check  # noqa: PLC0415
    from agents_orchestrator.security_modernization_agent.security_document import security_markdown  # noqa: PLC0415
    from config.ws_helper import get_session_id  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_sign()):
        return why
    ctx, why = await module_context(module_id)
    if ctx is None:
        return why
    mig, why = await _migration(module_id)
    if mig is None:
        return why
    if mig.ledger.get("state") != "in_review":
        return f"{module_id} is {mig.ledger.get('state')}; a security report is submitted while the module is in review."
    diff, why = diff_of(mig)
    if diff is None:
        return f"NOT SUBMITTED — {why}"
    state = read_json(_state_path(mig)) or {}
    if "carryover" not in state:
        return "NOT SUBMITTED — check the legacy secrets against the target first."
    http = [c["id"] for c in ctx["contracts"] if c.get("kind") == "http"]
    if http and "authz" not in state:
        return "NOT SUBMITTED — check the authorization of the module's HTTP contracts first."
    report = {"verdict": verdict, "rationale": rationale, "findings": findings or [], "contract_authz": contract_authz or []}
    try:
        artifact = build_artifact(module_id=module_id, report=report, mig=mig, ctx=ctx, state=state,
                                  legacy=read_json(_legacy_path(mig)) or {}, diff=diff,
                                  recorded_at=datetime.now(timezone.utc).isoformat(), session=str(get_session_id() or ""))
    except Exception as exc:  # noqa: BLE001 — a malformed argument the model sent
        return f"NOT SUBMITTED — the report could not be built: {type(exc).__name__}: {str(exc)[:300]}"
    handover = security_packet(artifact, {"version": 1, "status": "draft"})
    problems = list(handover.problems)
    wave = next((w for w in ctx.get("waves") or [] if w.get("id") == mig.ledger.get("wave")), {})
    problems += check(report=artifact, target_hits=diff["target"], carryover=state.get("carryover") or [],
                      http_contracts=http, authz=state.get("authz") or {}, wave_ends=str(wave.get("ends") or ""))
    if problems:
        return "NOT SUBMITTED — " + "\n".join(f"- {p}" for p in problems[:16])
    saved = await _persist(artifact)
    version = await freeze_version(STAGE, artifact)
    await _audit("modernization.security_submitted", module_id, {"verdict": verdict, "head": mig.head, "version": version})
    return (f"{security_markdown(artifact)}\n\n_{saved_line(saved, version, 'security report')}_\n\n"
            "The Security Engineer accepts it on the Security page; accepting records the sign-off on the ledger.")


@tool
async def export_security_document(module_id: str, filename: str = "security-report.docx") -> str:
    """Export a module's newest security report as a document (.docx, .pdf or .md)."""
    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from agents_orchestrator.security_modernization_agent.security_document import security_markdown  # noqa: PLC0415
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
        return f"{module_id} has no security report yet."
    name = normalise_filename(filename, "security-report.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(security_markdown(row.payload), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(name, url, ["The report VERSION on the page is what gets accepted."])


def _ledger_tool():
    from agents_orchestrator.development_modernization_agent.tools.migration_tools import get_ledger  # noqa: PLC0415

    return get_ledger


READ_TOOLS = make_review_read_tools(STAGE, LABEL)
TOOLS = [_ledger_tool(), *READ_TOOLS, scan_migrated_module, scan_legacy_baseline, diff_findings, check_secret_carryover,
         check_contract_authz, submit_security_report, export_security_document]
