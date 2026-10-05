"""Tools of the Equivalence Testing agent — Verify mode (Track 3, Phase J).

  read      `get_verification_plan` — the module in `verifying`, the ACCEPTED migration record (the head Review
            and Security signed off), the accepted baseline, the module's criteria, the scenarios that record
            them, and what will run. Read-only.
  run       `run_verification` — CONSEQUENTIAL: the legacy checkout with the module (and root shared build
            files) from that head, run TWICE in the baseline's sandbox; compared with the baseline's run 1,
            criterion by criterion, after only each criterion's own rules (`analysis/verify.py`); performance
            criteria timed on BOTH sides under the same load. Shapes only.
  record    `record_equivalence_results` — the verdicts as the tools computed them (the agent may only
            re-classify a regression as an accepted change, citing an ADR on the module); frozen as the next
            version (one version = one module's verification). Accepting it writes the ledger.

The model never states a verdict, a count or a latency: the run is kept beside the review checkout and the
record tool reads it back.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import shutil
import uuid
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from agents_orchestrator.modernization_common import review_checkout as RC

logger = logging.getLogger(__name__)

STAGE = "testing_modernization"
LABEL = "Equivalence Testing"
PERF_REPEAT = 20


def _scope() -> tuple[str, str, str]:
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    return str(get_tenant_id() or ""), str(get_project_id() or ""), str(get_user_id() or "")


def _page_only() -> Optional[str]:
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run():
        return ("Modules are verified on the Equivalence Testing page, against the ACCEPTED baseline and the accepted "
                "migration. Open the page to verify; here I can explain.")
    return None


def _state_path(project: str, module_id: str, head: str) -> pathlib.Path:
    return RC.checkout_dir(project, STAGE, module_id, head) / "verification.json"


def _read(path: pathlib.Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _write(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


async def _context(module_id: str, clone: bool = True) -> tuple[Optional[dict], str]:
    """Everything a verification needs, or why not (in words)."""
    from agents_orchestrator.modernization_common.review_tools import module_context  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import _inputs, _store  # noqa: PLC0415

    ctx, why = await module_context(module_id)
    if ctx is None:
        return None, why
    ins = await _inputs()
    design = ins["design_modernization"].stored or {}
    baseline_in = await _baseline()
    if baseline_in is None:
        return None, "There is no ACCEPTED baseline: a module is verified against the baseline QA accepted."
    baseline, baseline_version = baseline_in
    placed = [p for p in baseline.get("placements") or [] if p.get("module_id") == module_id]
    if not placed:
        return None, f"The accepted baseline (v{baseline_version}) has no recordings for {module_id}."
    mig, why = await RC.open_migration(STAGE, module_id, LABEL, clone=clone)
    if mig is None:
        return None, why
    capture_id = (baseline.get("capture") or {}).get("id") or ""
    _t, project, _u = _scope()
    store = _store()
    try:
        manifest = store.read_manifest(project, capture_id)
    except ValueError:
        manifest = None
    run1 = store.capture_dir(project, capture_id) / "run1" if manifest else None
    if run1 is None or not run1.is_dir():
        return None, "The accepted baseline's recordings are not in the baseline store any more: capture it again."
    ec_ids = [c["id"] for c in ctx["criteria"]]
    mapping = {ec: list(sc) for ec, sc in (baseline.get("mapping") or {}).items() if ec in ec_ids}
    return {"ctx": ctx, "design": design, "baseline": baseline, "baseline_version": baseline_version, "mig": mig,
            "baseline_run1": run1, "mapping": mapping, "capture_id": capture_id, "project": project}, ""


async def _baseline() -> Optional[tuple[dict, int]]:
    """The newest ACCEPTED baseline (never a verification), as stored, with its version."""
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415

    tenant, project, _u = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        row = await svc.latest_published(db, project, STAGE, subject="baseline")
    return (row.payload or {}, row.version) if row is not None and row.payload else None


def plan_markdown(c: dict, perf_mapping: dict) -> str:
    ctx, mig = c["ctx"], c["mig"]
    lines = [f"# Verifying {mig.module_id} {ctx.get('name') or ''} — `{mig.module_path}/`", "",
             f"Ledger: **{mig.ledger.get('state')}**. Migration record v{mig.version} (accepted), head `{mig.head[:10]}`, "
             f"pull request {mig.record.get('pr_url') or mig.ledger.get('prUrl') or '—'}.",
             f"Against the accepted baseline v{c['baseline_version']} (capture {c['capture_id']}).", "",
             "| Criterion | Comparison | Scenarios | Normalization |", "|---|---|---|---|"]
    for cr in ctx["criteria"]:
        if cr.get("comparison") == "percentile_threshold":
            sc = ", ".join(perf_mapping.get(cr["id"]) or []) or "— (name the HTTP scenario to time)"
            lines.append(f"| {cr['id']} {cr.get('observable')} | {cr.get('threshold')} | timed: {sc} | — |")
        else:
            sc = ", ".join(c["mapping"].get(cr["id"]) or []) or "— none recorded it (not run)"
            rules = ", ".join(r.get("field") for r in cr.get("normalization") or []) or "none"
            lines.append(f"| {cr['id']} {cr.get('observable')} | {cr.get('comparison')} | {sc} | {rules} |")
    lines += ["", "The run: the legacy system with this module (and the root build files) taken from the accepted head, "
                  "twice, in the same sandbox as the baseline (no network, synthetic data, stubs). Performance: both "
                  f"sides, the same requests {PERF_REPEAT} times, the same limits. Running it is consequential: ask first."]
    if mig.ledger.get("state") != "verifying":
        lines.insert(3, f"NOT READY: {mig.module_id} is {mig.ledger.get('state')}; a module is verified once Review "
                        "approves it and Security signs it off (verifying).")
    return "\n".join(lines)


@tool
async def get_verification_plan(module_id: str, perf_mapping: Optional[dict] = None) -> str:
    """What verifying a module will run: the accepted migration and baseline, each criterion with the scenarios
    that record it and its rules, and the performance criteria with the scenario timed
    (perf_mapping: {"EC-04": ["claims-read"]}). Read-only; show it before running."""
    c, why = await _context(module_id, clone=False)
    if c is None:
        return why
    return plan_markdown(c, dict(perf_mapping or {}))


def _perf_scenarios(c: dict, perf_mapping: dict, scenarios: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    by_id = {s["id"]: s for s in scenarios}
    out, problems = {}, []
    perf_ecs = {cr["id"] for cr in c["ctx"]["criteria"] if cr.get("comparison") == "percentile_threshold"}
    for ec, sids in (perf_mapping or {}).items():
        if ec not in perf_ecs:
            problems.append(f"{ec} is not a performance criterion of this module.")
            continue
        chosen = [by_id[s] for s in sids if s in by_id and by_id[s]["kind"] == "http"]
        if len(chosen) != len(sids):
            problems.append(f"{ec}: time HTTP scenarios of the capture profile ({', '.join(sorted(k for k, v in by_id.items() if v['kind'] == 'http'))}).")
            continue
        out[ec] = chosen
    return out, problems


def _run(c: dict, profile: dict, legacy: pathlib.Path, perf_mapping: dict, work: pathlib.Path) -> dict:
    """The consequential part, in a thread: overlay, two runs, compare, time. Returns shapes and numbers."""
    from agents_orchestrator.development_modernization_agent.preview import overlay  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.analysis import verify as V  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import profile as P  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import runner  # noqa: PLC0415

    mig = c["mig"]
    taken = overlay(legacy, mig.target, mig.module_path, work / "overlay")
    checked, problems = P.validate(profile, work / "overlay")
    if problems:
        raise runner.CaptureFailed("The migrated module cannot run in the sandbox as it is: " + "; ".join(problems[:6]))
    wanted = {s for sids in c["mapping"].values() for s in sids}
    scenarios = [s for s in checked["scenarios"] if s["id"] in wanted]
    run_id = f"ver-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    runner.capture(work / "overlay", {**checked, "scenarios": scenarios}, work / "out", run_id, 2)
    diffs = V.compare_runs(c["baseline_run1"], work / "out" / "run1", work / "out" / "run2", scenarios) if scenarios else {}
    perf_sc, _ = _perf_scenarios(c, perf_mapping, checked["scenarios"])
    perf: dict[str, dict] = {}
    if perf_sc:
        timed = {s["id"]: s for ss in perf_sc.values() for s in ss}
        legacy_profile, _ = P.validate(profile, legacy)
        lt = runner.measure(legacy, legacy_profile, list(timed.values()), run_id + "-pl", PERF_REPEAT, work / "perf-legacy")
        tt = runner.measure(work / "overlay", checked, list(timed.values()), run_id + "-pt", PERF_REPEAT, work / "perf-target")
        for ec, ss in perf_sc.items():
            l_ms = [x for s in ss for x in lt[s["id"]]["ms"]]
            t_ms = [x for s in ss for x in tt[s["id"]]["ms"]]
            perf[ec] = {"legacy_p95_ms": V.p95(l_ms), "target_p95_ms": V.p95(t_ms), "samples": len(t_ms),
                        "errors": {"legacy": sum(lt[s["id"]]["errors"] for s in ss),
                                   "target": sum(tt[s["id"]]["errors"] for s in ss)}}
    return {"id": run_id, "taken": taken, "scenarios": [{"id": s["id"], "kind": s["kind"]} for s in scenarios],
            "diffs": {sid: [a, b] for sid, (a, b) in diffs.items()}, "perf": perf}


def result_markdown(result: dict, module_id: str, verdict: str) -> str:
    lines = [f"# Verification of {module_id} — {verdict.upper()}", "",
             "| Criterion | Verdict | Cases | Normalization applied |", "|---|---|---:|---|"]
    for c in result["criteria"]:
        lines.append(f"| {c['ec_id']} | {c['verdict'].replace('_', ' ')} | {c['cases_compared'] if c['cases_compared'] is not None else '—'} | "
                     f"{', '.join(c['normalization_applied']) or '—'} |")
    if result["performance"]:
        lines += ["", "| Performance | Legacy p95 | Target p95 | Threshold |", "|---|---:|---:|---:|"]
        for p in result["performance"]:
            ms = lambda v: "not measured" if v is None else f"{v} ms"  # noqa: E731
            lines.append(f"| {p['ec_id']} | {ms(p['legacy_p95_ms'])} | {ms(p['target_p95_ms'])} | {p['threshold_ms']} ms |")
    if result["differences"]:
        lines += ["", "| Id | Criterion | Kind | Field | Cases | Shape (baseline vs target) | Likely area |", "|---|---|---|---|---:|---|---|"]
        lines += [f"| {d['id']} | {d['ec_id']} | {d['classification'].replace('_', ' ')} | {d['field']} | {d['cases']} | "
                  f"{d['masked_example']} | {d.get('likely_area') or '—'} |" for d in result["differences"]]
    else:
        lines += ["", "No difference after each criterion's own normalization."]
    if result["rule_proposals"]:
        lines += ["", "Proposed to Migration Strategy (never applied here): " + "; ".join(
            f"{r['ec_id']} {r['field']}" for r in result["rule_proposals"])]
    return "\n".join(lines)


@tool
async def run_verification(module_id: str, perf_mapping: Optional[dict] = None) -> str:
    """CONSEQUENTIAL — run the migrated module (the accepted head, overlaid on the legacy system) twice in the
    baseline's sandbox, compare every criterion with the accepted baseline, and time the performance criteria
    on both sides (perf_mapping: {"EC-04": ["claims-read"]}). Only after showing the plan and the user's yes on
    THIS turn. Returns criterion verdicts and differences as shapes, never values."""
    from agents_orchestrator.testing_modernization_agent.analysis import verify as V  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import runner  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import _load_profile, _may_capture  # noqa: PLC0415

    if why := _page_only():
        return why
    ok, why = await _may_capture()
    if not ok:
        return why.replace("captures a baseline", "verifies a module")
    c, why = await _context(module_id)
    if c is None:
        return why
    if c["mig"].ledger.get("state") != "verifying":
        return (f"{module_id} is {c['mig'].ledger.get('state')}; a module is verified once Review approves it and Security "
                "signs it off (verifying).")
    profile, problems, _src, legacy = _load_profile()
    if profile is None or problems or legacy is None:
        return "The capture profile cannot be used: " + "; ".join(problems[:5])
    perf_mapping = dict(perf_mapping or {})
    _p, perf_problems = _perf_scenarios(c, perf_mapping, profile["scenarios"])
    if perf_problems:
        return "Not run — " + " ".join(perf_problems)
    work = RC.checkout_dir(c["project"], STAGE, module_id, c["mig"].head).parent / f"work-{uuid.uuid4().hex[:8]}"
    try:
        try:
            run = await asyncio.to_thread(_run, c, profile, legacy, perf_mapping, work)
        except runner.CaptureFailed as exc:
            reason = str(exc).replace("The legacy service", "The service with the migrated module")
            return f"The verification could not run the migrated system: {reason}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    noise = {s["id"]: sorted((s.get("varying") or {}).keys()) for s in c["baseline"].get("scenarios") or []}
    result = V.evaluate(criteria=c["ctx"]["criteria"], mapping=c["mapping"],
                        diffs={k: tuple(v) for k, v in run["diffs"].items()}, noise=noise, design=c["design"],
                        perf=run["perf"])
    state = {"run": {k: run[k] for k in ("id", "taken", "scenarios", "perf")}, "diffs": run["diffs"], "noise": noise,
             "baseline_version": c["baseline_version"], "head": c["mig"].head, "migration_version": c["mig"].version,
             "perf_mapping": perf_mapping, "at": datetime.now(timezone.utc).isoformat()}
    _write(_state_path(c["project"], module_id, c["mig"].head), state)
    return result_markdown(result, module_id, V.module_verdict(result["criteria"])) + \
        "\n\nRecord it to put it up for acceptance (QA who did not run it, or a Project Admin)."


def build_artifact(*, module_id: str, c: dict, state: dict, result: dict, recorded_at: Optional[str],
                   session: str = "") -> dict:
    """The stored verification (`VerificationArtifact`) — ONE builder, for the record tool and the view fixtures."""
    from agents_orchestrator.testing_modernization_agent.analysis import verify as V  # noqa: PLC0415
    from shared.models.artifacts import VerificationArtifact  # noqa: PLC0415

    mig, ctx = c["mig"], c["ctx"]
    bl_ids = sorted({b for p in c["baseline"].get("placements") or [] if p.get("module_id") == module_id
                     for b in p.get("baseline_ids") or []})
    scenarios = []
    for sid, (a, b) in state["diffs"].items():
        scenarios.append({"id": sid, "cases": a.get("cases"), "run1_fields": sorted(a.get("varying") or {}),
                          "run2_fields": sorted(b.get("varying") or {})})
    return VerificationArtifact(
        module_id=module_id, pr=mig.record.get("pr_url") or mig.ledger.get("prUrl") or f"{mig.branch}@{mig.head[:10]}",
        baselines_replayed=[{"id": b, "version": c["baseline_version"]} for b in bl_ids],
        criteria=result["criteria"], differences=result["differences"], performance=result["performance"],
        rule_proposals=result["rule_proposals"], runs=2, module_verdict=V.module_verdict(result["criteria"]),
        migration_version=mig.version, head_sha=mig.head, baseline_version=c["baseline_version"],
        module={"name": ctx.get("name"), "legacy_path": mig.module_path,
                "criterion_ids": [x["id"] for x in ctx["criteria"]]},
        sources={**ctx["sources"], "migration": {"version": mig.version, "status": mig.status},
                 "baseline": {"version": c["baseline_version"], "status": "published"}},
        scenarios=sorted(scenarios, key=lambda s: s["id"]), perf_samples=(state.get("run") or {}).get("perf") or {},
        notes=[f"Run {(state.get('run') or {}).get('id')}: the legacy system with "
               f"{', '.join((state.get('run') or {}).get('taken') or [])} from the accepted head, twice."],
        system_name=ctx.get("system_name") or "", recorded_at=recorded_at, agent_session_id=session or None,
    ).model_dump(mode="json")


@tool
async def record_equivalence_results(module_id: str, accepted_changes: Optional[dict] = None) -> str:
    """Record the module's verification as the next version (one version = one module). The verdicts, counts,
    shapes and latencies are the run's — not yours. accepted_changes: {"EQ-001": "ADR-03"} only for a regression
    an ADR on this module explicitly allows. Accepting the version (QA who did not run it, or a Project Admin)
    writes the module's verdict on the ledger."""
    from agents_orchestrator.modernization_common.handover.emit import verification_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.analysis import verify as V  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import _has_capture_role  # noqa: PLC0415
    from config.ws_helper import get_session_id  # noqa: PLC0415

    if why := _page_only():
        return why
    if not await _has_capture_role():
        return "Only QA or a Project Admin of this project records a verification."
    c, why = await _context(module_id, clone=False)
    if c is None:
        return why
    if c["mig"].ledger.get("state") != "verifying":
        return f"{module_id} is {c['mig'].ledger.get('state')}; results are recorded while it is verifying."
    state = _read(_state_path(c["project"], module_id, c["mig"].head))
    if state is None:
        return f"{module_id} has not been verified at the accepted head {c['mig'].head[:10]}: run the verification first."
    if state.get("baseline_version") != c["baseline_version"]:
        return "The accepted baseline changed since this run: verify again."
    result = V.evaluate(criteria=c["ctx"]["criteria"], mapping=c["mapping"],
                        diffs={k: tuple(v) for k, v in state["diffs"].items()}, noise=state.get("noise") or {},
                        design=c["design"], perf=(state.get("run") or {}).get("perf"))
    module_adrs = [a["id"] for a in c["ctx"]["adrs"]]
    problems = V.apply_accepted(result, dict(accepted_changes or {}), module_adrs)
    if problems:
        return "NOT RECORDED — " + "\n".join(f"- {p}" for p in problems)
    artifact = build_artifact(module_id=module_id, c=c, state=state, result=result,
                              recorded_at=datetime.now(timezone.utc).isoformat(), session=str(get_session_id() or ""))
    handover = verification_packet(artifact, {"version": 1, "status": "draft"})
    if not handover.ok:
        return "NOT RECORDED — " + "\n".join(f"- {p}" for p in handover.problems[:12])
    saved = await _persist(artifact)
    version = await freeze_version(STAGE, artifact)
    return (f"{result_markdown(result, module_id, artifact['module_verdict'])}\n\n_{saved_line(saved, version, 'verification')}_\n\n"
            "QA who did not run it, or a Project Admin, accepts it on the Equivalence Testing page; accepting records "
            f"{module_id} as {artifact['module_verdict']} on the ledger.")


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the module's current verification."
    except Exception as exc:  # noqa: BLE001
        logger.exception("equivalence testing: persisting the verification failed")
        return f"Not saved ({type(exc).__name__}) — the result below is still complete."


TOOLS = [get_verification_plan, run_verification, record_equivalence_results]
