"""Tools of the Equivalence Testing agent — Baseline mode (Track 3, Phase G).

  read      the migration plan and the target design THIS TURN pinned (their hand-over packets),
            and the module ledger.
  profile   how the legacy system is built, seeded, started and exercised (`sandbox/profile.py`):
            the project's saved profile, else `sdlc-sandbox.json` in the legacy checkout.
  plan      `plan_capture` — which scenarios record which criterion, checked, shown before anything runs.
  capture   `capture_baseline` — CONSEQUENTIAL: runs the legacy system twice in the sandbox
            (`sandbox/runner.py`; no internet, synthetic data, stubs for external services), then
            compares the runs (`analysis/noise.py`). The model sees counts, field names and masked
            SHAPES — never a recording.
  record    `record_baseline` — BL-xx per module and scenario set, the noise report, the rule
            proposals to Migration Strategy (never a rule applied here), what was not captured and
            why; frozen as the next version.

The ledger is NOT written here: approving the version moves each baselined module
`sequenced → baselined` (the publish route, in its transaction).
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import shutil
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

STAGE = "testing_modernization"
FILE_SEGMENT = "testing_modernization_agent"
PLAN, DESIGN = "strategy", "design_modernization"
INPUTS = [PLAN, DESIGN]
CAPTURE_ROLES = {"qa", "project_admin"}
_SHOWN_PROBLEMS = 14
_LOCKS: dict[str, asyncio.Lock] = {}


def _session_key() -> str:
    from config.ws_helper import get_session_id  # noqa: PLC0415

    return str(get_session_id() or "default")


async def _inputs():
    from agents_orchestrator.modernization_common.inputs import read_inputs  # noqa: PLC0415

    return await read_inputs(INPUTS)


def _missing(item) -> str:
    from agents_orchestrator.modernization_common.inputs import missing_line  # noqa: PLC0415

    return missing_line(item)


def _store():
    from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore  # noqa: PLC0415

    return LocalBaselineStore()


def _approved(item) -> bool:
    return item.version is not None and item.status in ("published", "granted")


def _checkout() -> tuple[Optional[pathlib.Path], Optional[dict], str]:
    """(checkout path, the pull, project id) this turn reads."""
    from agents_orchestrator.modernization_common import legacy_code  # noqa: PLC0415

    project_id, run_id = legacy_code.current_scope()
    if not project_id:
        return None, None, ""
    pull = legacy_code.current_pull(project_id, run_id)
    return (legacy_code.checkout_dir(project_id, run_id) if pull else None), pull, project_id


def _load_profile() -> tuple[Optional[dict], list[str], str, Optional[pathlib.Path]]:
    """(profile, problems, where it came from, checkout)."""
    from agents_orchestrator.testing_modernization_agent.sandbox import profile as P  # noqa: PLC0415

    checkout, _pull, project_id = _checkout()
    if checkout is None:
        return None, ["The legacy code has not been pulled for this project — pull it first (the Pull legacy code "
                      "button, or ask me)."], "", None
    saved = _store().profile_path(project_id)
    if saved.is_file():
        raw, source = json.loads(saved.read_text(encoding="utf-8")), "saved for this project"
    elif (checkout / P.PROFILE_FILE).is_file():
        try:
            raw, source = json.loads((checkout / P.PROFILE_FILE).read_text(encoding="utf-8")), f"{P.PROFILE_FILE} in the legacy code"
        except json.JSONDecodeError:
            return None, [f"{P.PROFILE_FILE} in the legacy code is not valid JSON."], "", checkout
    else:
        return None, [f"There is no capture profile: the legacy code has no {P.PROFILE_FILE} and none was saved "
                      "for this project. Read the code (its Dockerfile, how it starts, its endpoints and jobs), "
                      "draft one with the user and save it with save_capture_profile."], "", checkout
    profile, problems = P.validate(raw, checkout)
    return profile, problems, source, checkout


async def _ledger_rows() -> dict[str, dict]:
    from config.ws_helper import get_project_id, get_tenant_id  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    async with get_db_session_for_tenant(str(get_tenant_id())) as db:
        return {r.module_id: ledger.as_dict(r) for r in await ledger.list_modules(db, str(get_project_id()))}


def _problems_text(head: str, problems: list[str], tail: str = "") -> str:
    shown = problems[:_SHOWN_PROBLEMS]
    more = f"\n…and {len(problems) - len(shown)} more." if len(problems) > len(shown) else ""
    return head + "\n" + "\n".join(f"- {p}" for p in shown) + more + (f"\n{tail}" if tail else "")


# ── reading ──────────────────────────────────────────────────────────────────


@tool
async def read_migration_plan() -> str:
    """The migration plan this baseline proves: every equivalence criterion (EC-xx) with its module,
    what it observes, its inputs, comparison and normalization rules, and the baseline plan (inputs,
    environment, data source, masking, due date). Call it first."""
    item = (await _inputs())[PLAN]
    if item.packet is None:
        return _missing(item)
    p = item.packet
    note = "" if _approved(item) else " A baseline is captured against an APPROVED plan only — this one is not yet."
    lines = [f"_This is {item.label}.{note}_", "",
             "| Criterion | Module | Observes | Inputs | Comparison | Normalization |", "|---|---|---|---|---|---|"]
    for c in p.get("equivalence_criteria") or []:
        rules = "; ".join(f"{r['field']}: {r['rule']}" for r in c.get("normalization") or []) or "—"
        lines.append(f"| {c['id']} | {c['module_id']} | {c['observable']} | {c['input_set']} | {c['comparison']} | {rules} |")
    if p.get("baseline_plan"):
        lines += ["", "Baseline plan:"]
        lines += [f"- {b['ec_id']}: {b['inputs']} — {b['environment']}; data {b['data_source']}, masking {b['masking']}; "
                  f"due {b['due']}" for b in p["baseline_plan"]]
    lines += ["", "Waves: " + "; ".join(f"{w['id']} {', '.join(w.get('modules') or []) or '(foundation)'}"
                                        for w in p.get("waves") or [])]
    return "\n".join(lines)


@tool
async def read_target_design() -> str:
    """The target design's frozen contracts (CT-xx), traps (TR-xx) and ADRs — which differences a
    later verification may accept (only an ADR allows one)."""
    item = (await _inputs())[DESIGN]
    if item.packet is None:
        return _missing(item)
    d = item.packet
    lines = [f"_This is {item.label}._", ""]
    lines += [f"- {c['id']} {c['name']} ({c.get('kind')}): {c.get('location') or ''}" for c in d.get("frozen_contracts") or []]
    lines += [f"- {t['id']} {t['change']}" for t in d.get("traps") or []]
    lines += [f"- {a['id']} {a['title']}" for a in d.get("adrs") or []]
    return "\n".join(lines) if len(lines) > 2 else lines[0] + "\n\nThe design names no contract, trap or ADR."


@tool
async def get_ledger() -> str:
    """Every module on the migration ledger: its state, wave, criteria and baselines. A module is
    baselined from `sequenced` (its plan approved)."""
    try:
        rows = await _ledger_rows()
    except Exception:  # noqa: BLE001
        logger.exception("equivalence testing: reading the ledger failed")
        return "The ledger could not be read just now (a database error). Try again."
    if not rows:
        return "No module is on the ledger yet — the target design and the migration plan are approved first."
    lines = ["| Module | State | Wave | Criteria | Baselines |", "|---|---|---|---|---|"]
    for m, r in sorted(rows.items()):
        lines.append(f"| {m} {r['moduleName']} | {r['state']} | {r.get('wave') or '—'} | "
                     f"{', '.join(r.get('ecIds') or []) or '—'} | {', '.join(r.get('baselineIds') or []) or '—'} |")
    return "\n".join(lines)


# ── the capture profile ─────────────────────────────────────────────────────


@tool
async def get_capture_profile() -> str:
    """How the legacy system is run in the sandbox: its build, seed, service, the external services
    that are stubbed, and the scenarios (http request sets, batch commands) a capture runs."""
    from agents_orchestrator.testing_modernization_agent.sandbox.profile import profile_markdown  # noqa: PLC0415

    profile, problems, source, _checkout_path = _load_profile()
    if profile is None:
        return problems[0]
    text = profile_markdown(profile, source)
    if problems:
        text += "\n\n" + _problems_text("It cannot be used as it is:", problems,
                                        "Fix these with the user, then save the corrected profile.")
    return text


@tool
async def save_capture_profile(profile: dict) -> str:
    """Save the capture profile for this project (when the legacy code has none, or it needs a
    change). ONE JSON object:
    {"version": 1, "data": "synthetic", "build": {"dockerfile": "Dockerfile"}, "writable": ["/data"],
     "seed": "command that creates the synthetic data", "service": {"command": "", "port": 8080, "health": "/health"},
     "stubs": [{"name": "fraudscore", "port": 9000, "env": "FRAUD_URL", "responses": "stubs/x.json"}],
     "scenarios": [{"id": "claims-read", "kind": "http", "requests": "scenarios/x.jsonl", "describes": ""},
                   {"id": "bank-file", "kind": "batch", "command": "", "outputs": ["/data/out/*.txt"], "describes": ""}]}
    Files are paths inside the legacy checkout. Show the user the profile and save it once they agree."""
    from agents_orchestrator.testing_modernization_agent.sandbox import profile as P  # noqa: PLC0415

    checkout, _pull, project_id = _checkout()
    if checkout is None:
        return "The legacy code has not been pulled for this project — pull it first."
    checked, problems = P.validate(profile, checkout)
    if problems:
        return _problems_text("NOT SAVED — the capture profile cannot be used as it is:", problems)
    path = _store().profile_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in profile.items()}
    path.write_text(json.dumps(clean, indent=1, sort_keys=True), encoding="utf-8")
    return "Saved for this project.\n\n" + P.profile_markdown(checked, "saved for this project")


# ── planning and capturing ──────────────────────────────────────────────────


async def _prepare(mapping: dict, not_captured: Optional[list]) -> tuple[Optional[dict], str]:
    """Everything a capture needs, checked — or why not. Returns ({plan, profile, checkout, ...}, "")."""
    from agents_orchestrator.testing_modernization_agent.analysis.baseline import check_mapping, criteria_by_id  # noqa: PLC0415
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run():
        return None, ("A baseline is captured on the Equivalence Testing page, against the project's APPROVED "
                      "migration plan — an Orchestrator conversation's plan is not approved. Open the page to capture.")
    ins = await _inputs()
    plan = ins[PLAN]
    if plan.packet is None:
        return None, _missing(plan)
    if not _approved(plan):
        return None, (f"Not yet: this is {plan.label}. A baseline records behaviour against the APPROVED plan's "
                      "criteria — ask the Architect to approve the plan on the Migration Strategy page first.")
    profile, problems, source, checkout = _load_profile()
    if profile is None or problems:
        return None, _problems_text("The capture profile cannot be used yet:", problems)
    found = check_mapping(plan.packet, [s["id"] for s in profile["scenarios"]], mapping, not_captured or [])
    if found:
        return None, _problems_text("The capture plan does not hold:", found)
    ecs = criteria_by_id(plan.packet)
    modules = sorted({ecs[ec]["module_id"] for ec in mapping} - {"all"})
    try:
        rows = await _ledger_rows()
    except Exception:  # noqa: BLE001
        logger.exception("equivalence testing: reading the ledger failed")
        return None, "The ledger could not be read just now (a database error). Try again."
    wrong = [f"{m} is {rows[m]['state'] if m in rows else 'not on the ledger'}" for m in modules
             if m not in rows or rows[m]["state"] not in ("sequenced", "baselined")]
    if wrong:
        return None, ("A module is baselined once its plan is approved (sequenced) and before its migration "
                      "starts: " + "; ".join(wrong) + ".")
    return {"plan": plan, "design": ins[DESIGN], "profile": profile, "source": source, "checkout": checkout,
            "modules": modules, "rows": rows}, ""


def _plan_markdown(ready: dict, mapping: dict, not_captured: list) -> str:
    profile = ready["profile"]
    by_id = {s["id"]: s for s in profile["scenarios"]}
    lines = [f"# Capture plan — {ready['plan'].label}", "",
             f"Runs the legacy system **twice** in an isolated sandbox (no internet), each time on a fresh copy "
             f"seeded with **{profile['data']}** data, and records every scenario of the profile "
             f"({ready['source']}). Modules: {', '.join(ready['modules']) or 'none (only all-module criteria)'}.", "",
             "| Criterion | Scenarios | Cases |", "|---|---|---:|"]
    for ec, scs in sorted(mapping.items()):
        lines.append(f"| {ec} | {', '.join(scs)} | {sum(int(by_id[s].get('cases') or 0) for s in scs)} |")
    if not_captured:
        lines += ["", "Not captured in Baseline mode: " + "; ".join(f"{n['ec_id']} ({n['reason']})" for n in not_captured)]
    if profile.get("stubs"):
        lines += ["", "External services answered by stubs: " + ", ".join(s["name"] for s in profile["stubs"]) + "."]
    lines += ["", "Running the legacy system is consequential: ask the user to go ahead, and capture only after "
                  "their yes on this turn."]
    return "\n".join(lines)


@tool
async def plan_capture(mapping: dict, not_captured: Optional[list] = None) -> str:
    """Check and show what a capture will run — nothing runs yet.

    Args:
        mapping: which scenarios record each criterion, {"EC-01": ["claims-read"], "EC-02": ["settle", "bank-file"]}.
            A module is baselined WHOLE: map every criterion of each module you touch (and every
            all-module criterion), or list it in not_captured.
        not_captured: criteria that cannot be recorded in Baseline mode, with why:
            [{"ec_id": "EC-05", "reason": "a load test — measured in Verify mode"}].
    """
    ready, why = await _prepare(mapping, not_captured)
    if ready is None:
        return why
    return _plan_markdown(ready, mapping, not_captured or [])


async def _may_capture() -> tuple[bool, str]:
    """QA or a Project Admin OF THIS PROJECT (permissions are a tenant-wide union), and their yes on
    this turn (the Consequential gate)."""
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415
    from shared.authz.consequential import authorize_consequential  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services.fallback_approval import project_roles  # noqa: PLC0415

    try:
        async with get_db_session_for_tenant(str(get_tenant_id())) as db:
            roles = await project_roles(db, tenant_id=str(get_tenant_id()), project_id=str(get_project_id()),
                                        user_id=str(get_user_id()))
    except Exception:  # noqa: BLE001 — cannot prove the role ⇒ refuse
        roles = set()
    if not roles & CAPTURE_ROLES:
        return False, "Only QA or a Project Admin of this project captures a baseline. Ask one of them to run it."
    return await authorize_consequential(
        STAGE, action="Running the legacy system to capture a baseline",
        ask="show the user the capture plan (plan_capture) and ask them to go ahead.")


def _capture_summary(manifest: dict, need: dict[str, list[str]]) -> str:
    lines = [f"# Capture {manifest['id']} — complete", "",
             f"Two runs of the legacy system (image `{manifest['imageId'][:19]}…`), every scenario recorded. "
             "Recordings stay in the sandbox store; below are counts, field names and masked shapes only.", "",
             "| Scenario | Cases | Fields that differed between the two runs |", "|---|---:|---|"]
    for sid, n in manifest["noise"].items():
        varying = ", ".join(f"{f} ({c}; {n['examples'][f][0]} vs {n['examples'][f][1]})" for f, c in n["varying"].items())
        lines.append(f"| {sid} | {n['cases']} | {varying or 'none — fully repeatable'} |")
    if need:
        lines += ["", "No normalization rule covers these, so each needs a rule PROPOSED to Migration Strategy "
                      "(field + rule) when you record the baseline — propose, never apply:"]
        lines += [f"- {ec}: {', '.join(fields)}" for ec, fields in need.items()]
    lines += ["", f"Record it with record_baseline(capture_id=\"{manifest['id']}\", rule_proposals=[...])."]
    return "\n".join(lines)


@tool
async def capture_baseline(mapping: dict, not_captured: Optional[list] = None) -> str:
    """CONSEQUENTIAL — run the legacy system twice in the sandbox and record every scenario. Only after
    plan_capture was shown and the user said yes on THIS turn. Same arguments as plan_capture.
    Returns counts, the fields that differed between the runs (masked) and the capture id."""
    from agents_orchestrator.testing_modernization_agent.analysis.baseline import uncovered  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.analysis.noise import compare  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import runner  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.store import new_capture_id, retain_until  # noqa: PLC0415
    from config.ws_helper import get_project_id, get_user_id  # noqa: PLC0415

    ready, why = await _prepare(mapping, not_captured)
    if ready is None:
        return why
    ok, why = await _may_capture()
    if not ok:
        return why
    project_id = str(get_project_id())
    lock = _LOCKS.setdefault(project_id, asyncio.Lock())
    if lock.locked():
        return "A capture is already running for this project — wait for it to finish."
    async with lock:
        store = _store()
        capture_id = new_capture_id()
        _checkout_path, pull, _pid = _checkout()
        started = datetime.now(timezone.utc)
        manifest = {"id": capture_id, "status": "running", "startedAt": started.isoformat(),
                    "requestedBy": str(get_user_id() or ""), "planVersion": ready["plan"].version,
                    "commit": (pull or {}).get("commit"), "profileSource": ready["source"],
                    "mapping": mapping, "notCaptured": list(not_captured or []),
                    "stubs": [s["name"] for s in ready["profile"].get("stubs") or []],
                    "scenarios": [{"id": s["id"], "kind": s["kind"], "cases": s.get("cases"),
                                   "describes": s.get("describes", "")} for s in ready["profile"]["scenarios"]]}
        store.write_manifest(project_id, capture_id, manifest)
        out = store.capture_dir(project_id, capture_id)
        try:
            result = await asyncio.to_thread(runner.capture, ready["checkout"], ready["profile"], out, capture_id)
            noise = await asyncio.to_thread(compare, out / "run1", out / "run2", ready["profile"]["scenarios"])
        except Exception as exc:  # noqa: BLE001 — a failed capture accepts nothing and keeps no partial recording
            reason = str(exc) if isinstance(exc, runner.CaptureFailed) else f"an unexpected error ({type(exc).__name__})"
            if not isinstance(exc, runner.CaptureFailed):
                logger.exception("equivalence testing: capture %s failed", capture_id)
            for sub in ("run1", "run2"):
                shutil.rmtree(out / sub, ignore_errors=True)
            finished = datetime.now(timezone.utc)
            manifest.update({"status": "failed", "error": reason[:500], "finishedAt": finished.isoformat(),
                             "retainUntil": retain_until(finished)})
            store.write_manifest(project_id, capture_id, manifest)
            return (f"Capture {capture_id} FAILED: {reason}\nNothing was recorded and no baseline was accepted; the "
                    "sandbox was removed. Tell the user what failed; fix the cause (often the profile) before trying again.")
        finished = datetime.now(timezone.utc)
        manifest.update({"status": "complete", "finishedAt": finished.isoformat(), "imageId": result["image_id"],
                         "runs": result["runs"], "noise": noise, "retainUntil": retain_until(finished)})
        store.write_manifest(project_id, capture_id, manifest)
        return _capture_summary(manifest, uncovered(ready["plan"].packet, mapping, noise))


# ── recording ────────────────────────────────────────────────────────────────


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the current baseline."
    except Exception as exc:  # noqa: BLE001
        logger.exception("equivalence testing: persisting the baseline failed")
        return f"Not saved ({type(exc).__name__}) — the baseline below is still complete."


def build_artifact(plan: dict, manifest: dict, proposals: list[dict], *, hash_of, region: str, sources: dict,
                   system_name: str, notes: list[str], recorded_at: Optional[str], session: str = "") -> dict:
    """The stored baseline (`EquivalenceArtifact`) — ONE builder, used by the record tool and the
    view-fixture generator."""
    from agents_orchestrator.testing_modernization_agent.analysis import baseline as B  # noqa: PLC0415
    from shared.models.artifacts import EquivalenceArtifact  # noqa: PLC0415

    payload = B.build(plan, manifest["mapping"], manifest["noise"], proposals, manifest.get("notCaptured") or [],
                      manifest.get("stubs") or [], hash_of, region, manifest["finishedAt"])
    return EquivalenceArtifact(
        **payload, system_name=system_name, sources=sources,
        capture={k: manifest.get(k) for k in ("id", "startedAt", "finishedAt", "imageId", "commit", "profileSource",
                                              "requestedBy", "runs")},
        mapping=manifest["mapping"],
        scenarios=[{**s, **{k: (manifest["noise"].get(s["id"]) or {}).get(k) for k in ("varying", "examples")}}
                   for s in manifest.get("scenarios") or []],
        placements=B.placements(payload), notes=notes, recorded_at=recorded_at, agent_session_id=session or None,
    ).model_dump(mode="json")


@tool
async def record_baseline(capture_id: str, rule_proposals: Optional[list] = None) -> str:
    """Record a COMPLETE capture as the baseline — the BL-xx the migration will be proven against.

    Args:
        capture_id: from capture_baseline.
        rule_proposals: one per field the capture listed as varying with no rule covering it, PROPOSED to
            Migration Strategy — [{"ec_id": "EC-01", "field": "requestId", "rule": "ignore the value, require it present"}].
            Never a field that did not vary; the evidence is written from the counts, not by you.
    """
    from agents_orchestrator.modernization_common.handover.emit import baseline_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.analysis.baseline import check_proposals  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.baseline_document import baseline_markdown  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.store import region  # noqa: PLC0415
    from config.ws_helper import get_project_id  # noqa: PLC0415

    project_id = str(get_project_id() or "")
    store = _store()
    manifest = store.read_manifest(project_id, capture_id) if project_id else None
    if manifest is None:
        return f"There is no capture {capture_id} for this project."
    if manifest.get("status") != "complete":
        return (f"Capture {capture_id} is {manifest.get('status')}: only a complete capture becomes a baseline"
                + (f" ({manifest.get('error')})." if manifest.get("error") else "."))
    ready, why = await _prepare(manifest["mapping"], manifest.get("notCaptured"))
    if ready is None:
        return why
    plan = ready["plan"]
    if plan.version != manifest.get("planVersion"):
        return (f"Capture {capture_id} recorded the criteria of plan v{manifest.get('planVersion')}, but the approved "
                f"plan is now v{plan.version}. Capture again against the current plan.")
    problems = check_proposals(plan.packet, manifest["mapping"], manifest["noise"], rule_proposals or [])
    if problems:
        return _problems_text("NOT RECORDED YET — the baseline cannot be handed to Migration Development as it is:",
                              problems, "Propose the missing rules (or correct them) and record again.")
    notes = [f"Captured from commit {str(manifest.get('commit'))[:10]} with {manifest['profileSource']}; data: synthetic."]
    if rule_proposals:
        notes.append(f"{len(rule_proposals)} normalization rule(s) proposed to Migration Strategy — the criteria they "
                     "belong to stay open until the plan is revised.")
    artifact = build_artifact(
        plan.packet, manifest, rule_proposals or [],
        hash_of=lambda scs: store.baseline_hash(project_id, capture_id, scs), region=region(),
        sources={"plan": {"version": plan.version, "status": plan.status},
                 "design": {"version": ready["design"].version, "status": ready["design"].status}},
        system_name=str((plan.stored or {}).get("system_name") or (ready["design"].stored or {}).get("system_name") or ""),
        notes=notes, recorded_at=datetime.now(timezone.utc).isoformat(), session=_session_key())
    handover = baseline_packet(artifact, {"version": 1, "status": "draft"})
    if not handover.ok:
        return _problems_text("NOT RECORDED YET:", handover.problems)
    manifest["keep"] = True
    store.write_manifest(project_id, capture_id, manifest)
    saved = await _persist(artifact)
    version = await freeze_version(STAGE, artifact)
    return f"{baseline_markdown(artifact)}\n\n_{saved_line(saved, version, 'baseline')}_"


@tool
async def export_baseline_document(filename: str = "baseline.docx") -> str:
    """Export the newest recorded baseline as a document (.docx, .pdf or .md) for sign-off."""
    import os  # noqa: PLC0415

    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.baseline_document import baseline_markdown  # noqa: PLC0415
    from config.ws_helper import get_project_id, get_tenant_id  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415
    from shared.tools.doc_export import (  # noqa: PLC0415
        export_result_message, normalise_filename, render_document, supported_list,
    )

    if not (get_project_id() and get_tenant_id()):
        return "No project is bound to this conversation."
    async with get_db_session_for_tenant(str(get_tenant_id())) as db:
        row = await svc.latest_version(db, str(get_project_id()), STAGE)
    if row is None or not row.payload:
        return "No baseline has been recorded yet — record it first."
    name = normalise_filename(filename, "baseline.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(baseline_markdown(row.payload), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(
        name, url, ["It is saved as a draft of the Equivalence Testing stage. The baseline VERSION on the page is "
                    "what gets accepted — by QA who did not record it, or a Project Admin."])


TOOLS = [read_migration_plan, read_target_design, get_ledger, get_capture_profile, save_capture_profile,
         plan_capture, capture_baseline, record_baseline, export_baseline_document]
