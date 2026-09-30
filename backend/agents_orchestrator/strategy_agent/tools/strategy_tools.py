"""Tools of the Migration Strategy agent (Track 3, Phase F).

  read      the brief, the assessment and the target design THIS TURN pinned
            (`modernization_common.inputs`), as their hand-over packets.
  compute   three deterministic tools the plan starts from — never the model's arithmetic:
            `propose_wave_order` (dependency graph + patterns + risk), `check_calendar` (the draft
            against the brief's dates and cutover window) and `estimate_effort` (a stated table).
  record    the plan: validated as the hand-over packet (`PlanPayload`), then against the three
            inputs (`analysis/checks.py`), the calendar recomputed so every conflict is proven
            reported; stored on the run, frozen as the next version, returned as the document.
  export    the recorded plan as Word, PDF or Markdown.
  board     one Feature per wave and one item per module, built from the RECORDED plan (never from
            the model's arguments), previewed first; writing is Consequential: an Architect or
            Project Admin OF THIS PROJECT, and their yes on this very turn.

The ledger is NOT written here: approval of the version places the modules (`sequenced`), in the
publish route's transaction.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from pydantic import ValidationError

logger = logging.getLogger(__name__)

STAGE = "strategy"
FILE_SEGMENT = "strategy_agent"
BRIEF, ASSESSMENT, DESIGN = "requirements_modernization", "discovery", "design_modernization"
INPUTS = [BRIEF, ASSESSMENT, DESIGN]

#: The last plan recorded in each Orchestrator conversation (page chats read the version store).
_LAST_PLAN: dict[str, dict] = {}
_SHOWN_PROBLEMS = 14


def _session_key() -> str:
    from config.ws_helper import get_session_id  # noqa: PLC0415

    return str(get_session_id() or "default")


async def _inputs():
    from agents_orchestrator.modernization_common.inputs import read_inputs  # noqa: PLC0415

    return await read_inputs(INPUTS)


def _missing(item) -> str:
    from agents_orchestrator.modernization_common.inputs import missing_line  # noqa: PLC0415

    return missing_line(item)


def _patterns(design: dict) -> dict[str, list[str]]:
    return {m["module_id"]: list(m.get("patterns") or []) for m in design.get("modules") or []}


def _edges(assessment: dict) -> list[tuple[str, str]]:
    return [(a, b) for a, b in assessment.get("graph") or []]


# ── reading ──────────────────────────────────────────────────────────────────


@tool
async def read_migration_brief() -> str:
    """The brief this plan works to: the deadline, budget, change-freeze date, cutover window,
    dated milestones, what must not change, and the success measures by kind. Call it first."""
    item = (await _inputs())[BRIEF]
    if item.packet is None:
        return _missing(item)
    p = item.packet
    lines = [f"_This is {item.label}._", "", f"**{p['system_name']}** — {p['goal']}", "",
             f"- Deadline: {p.get('deadline') or 'no dated deadline'}",
             f"- Budget: {p.get('budget') or 'not stated'}",
             f"- Legacy change freeze from: {p.get('freeze_from') or 'no freeze date given'}",
             f"- Cutover window: {p.get('downtime_window') or 'not stated'}",
             f"- Data residency: {p.get('data_residency') or 'not stated'}",
             f"- In scope: {'; '.join(p['scope']['in'])}", f"- Out of scope: {'; '.join(p['scope'].get('out') or []) or '—'}",
             f"- Constraints: {'; '.join(p.get('constraints') or []) or '—'}"]
    if p.get("milestones"):
        lines += ["", "Dated milestones (the user's dates — never move one):"]
        lines += [f"- {m['date']} {m['label']} ({m['kind']})" for m in p["milestones"]]
    lines += ["", "Success measures (equivalence, performance and security ones each need a criterion, "
              "protects_measures holding exactly these words):"]
    lines += [f"- [{m['kind']}] “{m['metric']}”: {m.get('today') or '?'} → {m['target']}" for m in p["success_measures"]]
    if p.get("must_not_change"):
        lines += ["", "Must not change: " + "; ".join(f"“{w}”" for w in p["must_not_change"])]
    return "\n".join(lines)


@tool
async def read_assessment() -> str:
    """The assessment the plan sequences: each module's id, tier, risk score and size, and the
    dependency graph. Its numbers are fixed — never change a tier or a score."""
    item = (await _inputs())[ASSESSMENT]
    if item.packet is None:
        return _missing(item)
    p = item.packet
    lines = [f"_This is {item.label}; commit `{str(p.get('commit'))[:10]}`._", "",
             "| Id | Module | Tier | Score | LOC | Fan-in |", "|---|---|---|---:|---:|---:|"]
    for m in p["modules"]:
        lines.append(f"| {m['id']} | {m['name']} | {m['tier']} | {m['score']} | "
                     f"{m['loc'] if m.get('loc') is not None else 'not measured'} | "
                     f"{m['fan_in'] if m.get('fan_in') is not None else '—'} |")
    graph = ", ".join(f"{a}→{b}" for a, b in p.get("graph") or []) or "no module depends on another"
    lines += ["", f"Dependencies (dependent→dependency): {graph}."]
    return "\n".join(lines)


@tool
async def read_target_design() -> str:
    """The target design the plan executes: the pattern per module, the interop plan and the
    ordering constraints, the frozen contracts (CT-xx) and traps (TR-xx) the criteria must protect,
    and the ADRs an order exception may cite."""
    item = (await _inputs())[DESIGN]
    if item.packet is None:
        return _missing(item)
    from agents_orchestrator.design_modernization_agent.design_document import design_markdown  # noqa: PLC0415

    return f"_This is {item.label}._\n\n" + design_markdown(item.stored or {})


# ── computing ────────────────────────────────────────────────────────────────


@tool
async def propose_wave_order() -> str:
    """The dependency-safe order the waves start from: dependencies first, cycles that must move
    together, lowest risk first within a level; modules the design keeps are left out. Call it
    before drafting waves, and give the reason for every change you make to it."""
    from agents_orchestrator.strategy_agent.analysis.ordering import order_markdown, propose_order  # noqa: PLC0415

    ins = await _inputs()
    for stage in (ASSESSMENT, DESIGN):
        if ins[stage].packet is None:
            return _missing(ins[stage])
    return order_markdown(propose_order(ins[ASSESSMENT].packet["modules"], _edges(ins[ASSESSMENT].packet),
                                        _patterns(ins[DESIGN].packet)))


@tool
async def check_calendar(plan: dict) -> str:
    """Lay a DRAFT plan against the brief's dates: waves ending after the deadline or a
    deadline/decommission milestone, baselines due after the freeze or after their wave starts,
    cutovers outside the brief's window. Returns every conflict with its ref — report each in
    calendar_conflicts with that ref.

    Args:
        plan: the draft, at least {"waves": [...], "equivalence_criteria": [...], "baseline_plan": [...]}
              in the record_migration_strategy shape.
    """
    from agents_orchestrator.strategy_agent.analysis.calendar import calendar_markdown, check_calendar as check  # noqa: PLC0415

    brief = (await _inputs())[BRIEF]
    if brief.packet is None:
        return _missing(brief)
    if not isinstance(plan, dict):
        return "Give the draft plan as one JSON object with its waves, criteria and baseline plan."
    try:
        return calendar_markdown(check(plan, brief.packet), brief.packet)
    except (KeyError, TypeError, AttributeError) as exc:  # an incomplete draft: say what is missing
        return (f"The draft could not be checked ({type(exc).__name__}: {exc}). Every wave needs an id, starts, ends "
                "and modules; every criterion an id and module_id; every baseline an ec_id and due date.")


@tool
async def estimate_effort(waves: Optional[list[dict]] = None) -> str:
    """Effort bands from a stated table (size × tier × pattern, ±30 %), per module and — given the
    draft waves ([{"id": "W1", "modules": ["M-05"]}, ...]) — per wave. An ESTIMATE; say so."""
    from agents_orchestrator.strategy_agent.analysis.effort import effort_markdown, estimate  # noqa: PLC0415

    ins = await _inputs()
    for stage in (ASSESSMENT, DESIGN):
        if ins[stage].packet is None:
            return _missing(ins[stage])
    try:
        return effort_markdown(estimate(ins[ASSESSMENT].packet["modules"], _patterns(ins[DESIGN].packet), waves or []))
    except (KeyError, TypeError, AttributeError) as exc:
        return (f"The waves could not be read ({type(exc).__name__}: {exc}). Give them as "
                "[{\"id\": \"W1\", \"modules\": [\"M-05\"]}, ...].")


# ── recording ────────────────────────────────────────────────────────────────


def check_plan(plan: dict, brief: dict, assessment: dict, design: dict) -> tuple[list[str], list[dict]]:
    """Every cross-artifact rule, in one place — (problems, the calendar conflicts it computed).
    `plan` is a validated PlanPayload dumped by alias; the rest are hand-over payloads."""
    from agents_orchestrator.strategy_agent.analysis import checks  # noqa: PLC0415
    from agents_orchestrator.strategy_agent.analysis.calendar import check_calendar as calendar  # noqa: PLC0415

    patterns = _patterns(design)
    computed = calendar(plan, brief)
    problems: list[str] = []
    problems += checks.check_waves(plan["waves"], patterns)
    problems += checks.check_order(plan["waves"], _edges(assessment), plan.get("order_exceptions") or [],
                                   {a["id"] for a in design.get("adrs") or []})
    problems += checks.check_coverage(plan.get("equivalence_criteria") or [], design, brief.get("success_measures") or [])
    problems += checks.check_exits(plan["waves"], plan.get("equivalence_criteria") or [])
    problems += checks.check_baselines(plan.get("equivalence_criteria") or [], plan.get("baseline_plan") or [])
    problems += checks.check_parallel_runs(plan["waves"], patterns)
    problems += checks.check_dates(plan, brief, computed)
    problems += checks.check_effort(plan, brief)
    return problems, computed


def placements(plan: dict) -> list[dict]:
    """Each planned module's wave and the criteria that prove it — what approval puts on the ledger."""
    criteria = plan.get("equivalence_criteria") or []
    shared = [c["id"] for c in criteria if c["module_id"] == "all"]
    return [{"module_id": m, "wave": w["id"], "patterns": list((w.get("patterns") or {}).get(m) or []),
             "ec_ids": [c["id"] for c in criteria if c["module_id"] == m] + shared}
            for w in plan["waves"] for m in w.get("modules") or []]


def build_artifact(data: dict, brief: dict, assessment: dict, design: dict, computed: list[dict], *,
                   sources: dict, notes: list[str], recorded_at: Optional[str], session: str = "") -> dict:
    """The stored plan (`StrategyArtifact`): the validated plan plus what code computed from the
    three inputs — ONE builder, used by the record tool and by the view-fixture generator."""
    from agents_orchestrator.strategy_agent.analysis.effort import estimate  # noqa: PLC0415
    from agents_orchestrator.strategy_agent.analysis.ordering import propose_order  # noqa: PLC0415
    from shared.models.artifacts import StrategyArtifact  # noqa: PLC0415

    return StrategyArtifact(
        **data,
        system_name=str(brief.get("system_name") or ""),
        sources=sources,
        placements=placements(data),
        proposed_order=propose_order(assessment["modules"], _edges(assessment), _patterns(design)),
        calendar_checked=computed,
        effort_table=estimate(assessment["modules"], _patterns(design), data["waves"]),
        brief_dates={**{k: brief.get(k) for k in ("deadline", "freeze_from", "downtime_window", "budget")},
                     "milestones": list(brief.get("milestones") or [])},
        notes=notes,
        recorded_at=recorded_at,
        agent_session_id=session or None,
    ).model_dump(mode="json")


def _refusal(problems: list[str]) -> str:
    shown = problems[:_SHOWN_PROBLEMS]
    more = f"\n…and {len(problems) - len(shown)} more." if len(problems) > len(shown) else ""
    return ("NOT RECORDED YET — the plan cannot be handed to Equivalence Testing and Migration Development as it is:\n"
            + "\n".join(f"- {p}" for p in shown) + more
            + "\nFix these and record the whole plan again. Where a fix needs the user (a date, a parallel-run "
              "length, who owns a wave), ask them — at most three questions at a time.")


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the current migration plan."
    except Exception as exc:  # noqa: BLE001 — the user still gets the document
        logger.exception("migration strategy: persisting the plan failed")
        return f"Not saved ({type(exc).__name__}) — the plan below is still complete."


@tool
async def record_migration_strategy(plan: dict) -> str:
    """Record the migration plan once the user agrees (or asks you to go ahead). Re-record the WHOLE
    plan to revise it; the newest version wins.

    `plan` is ONE JSON object:
    {
      "summary": "2-4 sentences",
      "waves": [{"id": "W0", "name": "Foundation", "modules": [], "patterns": {},
                 "starts": "YYYY-MM-DD", "ends": "YYYY-MM-DD", "date_status": "given|proposed",
                 "entry_criteria": [""], "exit_criteria": ["EC-01", "security sign-off"],
                 "parallel_run": {"required": false, "period": "", "system_of_record": "legacy|new"},
                 "cutover_window": "Sun 14 Feb 2027 00:00–02:00",
                 "rollback": {"trigger": "", "method": "", "max_time": ""}, "owner": "", "order_reason": ""},
                {"id": "W1", "modules": ["M-05"], "patterns": {"M-05": ["the design's patterns"]}, ...}],
      "order_exceptions": [{"module_id": "M-02", "depends_on": "M-01", "reason": "", "adr_id": "ADR-02"}],
      "equivalence_criteria": [{"id": "EC-01", "module_id": "M-01" | "all",
                                "protects": ["CT-01", "TR-02"], "protects_measures": ["the brief's words"],
                                "observable": "", "input_set": "",
                                "comparison": "exact|byte_identical|numeric_tolerance|schema_equal|set_equal|percentile_threshold",
                                "normalization": [{"field": "", "rule": "", "reason": ""}], "threshold": ""}],
      "baseline_plan": [{"ec_id": "EC-01", "inputs": "", "environment": "", "data_source": "", "masking": "",
                         "due": "YYYY-MM-DD"}],
      "freeze_policy": {"from": "YYYY-MM-DD", "allowed": "", "carry_forward": ""},
      "critical_path": [""],
      "calendar_conflicts": [{"conflict": "", "impact": "", "options": [""], "resolution": "", "ref": "from check_calendar"}],
      "raid": {"risks": [{"risk": "", "evidence": "", "mitigation": ""}], "assumptions": [""], "issues": [""],
               "dependencies": [""]},
      "effort": [{"wave": "W1", "band": "", "basis": ""}],
      "budget_fit": ""
    }
    It refuses — naming each problem — a moved module in no wave, a module the design keeps in a
    wave, a pattern that differs from the design's, a module before what it depends on without an
    order exception citing a design ADR, a contract, trap or equivalence/performance/security
    measure no criterion protects, a wave whose exits omit its modules' criteria, a contract/trap
    criterion without a baseline, a parallel run without its period, a freeze date other than the
    brief's, an unreported calendar conflict, a wave without effort, a budget without an answer.
    """
    from agents_orchestrator.modernization_common.handover.emit import _problems, plan_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.handover.packets import PlanPayload  # noqa: PLC0415

    if not isinstance(plan, dict):
        return "NOT RECORDED YET — `plan` must be one JSON object (see the tool's description)."
    ins = await _inputs()
    missing = [_missing(ins[s]) for s in INPUTS if ins[s].packet is None]
    if missing:
        return ("NOT RECORDED — a migration plan is checked against the brief, the assessment and the target design:\n"
                + "\n".join(f"- {m}" for m in missing) + "\nTell the user what is needed; do not record a plan without them.")
    try:
        payload = PlanPayload.model_validate(plan)
    except ValidationError as exc:
        return _refusal(_problems(exc))
    data = payload.model_dump(mode="json", by_alias=True)
    brief, assessment, design = ins[BRIEF].packet, ins[ASSESSMENT].packet, ins[DESIGN].packet
    problems, computed = check_plan(data, brief, assessment, design)
    if problems:
        return _refusal(problems)

    from agents_orchestrator.strategy_agent.analysis.calendar import window_unread  # noqa: PLC0415

    notes = []
    for stage in INPUTS:
        if ins[stage].version is not None and ins[stage].status == "draft":
            notes.append(f"Built from {ins[stage].label}: the plan is provisional until it is approved.")
    unread = window_unread(brief)
    if unread:
        notes.append(f"The cutover window “{brief['downtime_window']}” could not be read as "
                     f"{' or '.join(unread)}, so cutovers were not checked for {' or '.join(unread)}.")
    open_ones = [c for c in data.get("calendar_conflicts") or [] if not (c.get("resolution") or "").strip()]
    if open_ones:
        notes.append(f"{len(open_ones)} calendar conflict(s) are still open — they need the user's decision.")
    artifact = build_artifact(
        data, brief, assessment, design, computed,
        sources={"brief": {"version": ins[BRIEF].version, "status": ins[BRIEF].status},
                 "assessment": {"version": ins[ASSESSMENT].version, "status": ins[ASSESSMENT].status,
                                "commit": assessment.get("commit")},
                 "design": {"version": ins[DESIGN].version, "status": ins[DESIGN].status}},
        notes=notes, recorded_at=datetime.now(timezone.utc).isoformat(), session=_session_key())
    handover = plan_packet(artifact, {"version": 1, "status": "draft"})
    if not handover.ok:  # the same model validated it above; a failure here is a bug, said plainly
        return _refusal(handover.problems)

    _LAST_PLAN[_session_key()] = artifact
    saved = await _persist(artifact)
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from agents_orchestrator.strategy_agent.strategy_document import strategy_markdown  # noqa: PLC0415

    version = await freeze_version(STAGE, artifact)
    return f"{strategy_markdown(artifact)}\n\n_{saved_line(saved, version, 'migration plan')}_"


# ── the recorded plan: export and board ─────────────────────────────────────


async def _recorded_plan(version: int = 0) -> tuple[Optional[dict], str, str]:
    """(plan, where it came from, its status). On a page: that version, or the newest. In an
    Orchestrator conversation: the plan saved on its run (so a restart or another worker still
    finds it), else the one recorded in this process; versions exist only on the page."""
    from config.ws_helper import get_orchestrator_run, get_project_id, get_run_id, get_tenant_id  # noqa: PLC0415

    if get_orchestrator_run() or not (get_project_id() and get_tenant_id()):
        if version:
            return None, (f"Plan versions exist on the Migration Strategy page, not in an Orchestrator "
                          f"conversation — there is one plan here, the one recorded in it. Leave version out, or "
                          f"write v{version} from the page."), ""
        plan = None
        run_id, tenant = get_run_id(), get_tenant_id()
        if run_id and tenant:
            try:
                import uuid  # noqa: PLC0415

                from sqlalchemy import select  # noqa: PLC0415

                from shared.db import get_db_session_for_tenant  # noqa: PLC0415
                from shared.models.orm import Run  # noqa: PLC0415

                async with get_db_session_for_tenant(str(tenant)) as db:
                    plan = (await db.execute(select(Run.strategy_artifacts)
                                             .where(Run.id == uuid.UUID(str(run_id))))).scalar_one_or_none()
            except Exception:  # noqa: BLE001
                logger.exception("migration strategy: reading the run's plan failed")
        plan = plan or _LAST_PLAN.get(_session_key())
        return plan, "the plan recorded in this conversation", "recorded"
    try:
        from shared.db import get_db_session_for_tenant  # noqa: PLC0415
        from shared.services import artifact_versions as svc  # noqa: PLC0415

        async with get_db_session_for_tenant(str(get_tenant_id())) as db:
            row = (await svc.get_version(db, str(get_project_id()), STAGE, int(version)) if version
                   else await svc.latest_version(db, str(get_project_id()), STAGE))
        if row is None or not row.payload:
            return None, "", ""
        state = "approved" if row.status == "published" else row.status
        return row.payload, f"migration plan v{row.version} ({state})", row.status
    except Exception:  # noqa: BLE001
        logger.exception("migration strategy: reading the recorded plan failed")
        return None, "", ""


@tool
async def export_strategy_document(filename: str = "migration_strategy.docx") -> str:
    """Export the recorded migration plan as a document the Architect can put forward for sign-off.
    Format follows the extension: .docx, .pdf, .md."""
    plan, why, _status = await _recorded_plan()
    if plan is None:
        return why or "No migration plan has been recorded yet — record it first."
    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from agents_orchestrator.strategy_agent.strategy_document import strategy_markdown  # noqa: PLC0415
    from shared.tools.doc_export import (  # noqa: PLC0415
        export_result_message, normalise_filename, render_document, supported_list,
    )

    name = normalise_filename(filename, "migration_strategy.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(strategy_markdown(plan), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(
        name, url, ["It is saved as a draft of the Migration Strategy stage. The plan VERSION on the page is what "
                    "gets signed off — an Architect who did not produce it, or a Project Admin."])


def work_items(plan: dict, feature_type: str = "Feature", item_type: str = "User Story") -> list[dict]:
    """The board items a plan becomes — one Feature per wave that moves something, one child per
    module with the criteria that prove it. Built from the RECORDED plan only."""
    criteria = {c["id"]: c for c in plan.get("equivalence_criteria") or []}
    placed = {p["module_id"]: p for p in plan.get("placements") or []}
    out = []
    for w in plan.get("waves") or []:
        if not w.get("modules"):
            continue
        rb = w.get("rollback") or {}
        feature = {
            "type": feature_type, "title": f"{w['id']} — {w.get('name')}",
            "description": (f"{w.get('starts')} → {w.get('ends')} ({w.get('date_status')}). "
                            f"Cutover: {w.get('cutover_window') or 'not set'}. "
                            f"Exit: {'; '.join(w.get('exit_criteria') or [])}. "
                            f"Rollback: when {rb.get('trigger')}, {rb.get('method')}."),
            "children": [],
        }
        for m in w["modules"]:
            ecs = placed.get(m, {}).get("ec_ids") or []
            feature["children"].append({
                "type": item_type,
                "title": f"Migrate {m} ({'+'.join((w.get('patterns') or {}).get(m, []))})",
                "description": "Done when: " + ("; ".join(f"{e} {criteria[e]['observable']} "
                                                            f"({criteria[e]['comparison']})" for e in ecs if e in criteria)
                                                or "its wave's exit criteria pass") + ".",
            })
        out.append(feature)
    return out


@tool
async def preview_wave_work_items(version: int = 0, feature_type: str = "Feature",
                                  item_type: str = "User Story") -> str:
    """Show EXACTLY what writing the plan to the board would create — read-only. Show this to the
    user and ask before create_wave_work_items.

    Args:
        version: the plan version (0 = the newest).
        feature_type / item_type: the board's work-item types (Azure DevOps Agile: Feature / User Story;
            Scrum: Feature / Product Backlog Item; Jira: Epic / Story).
    """
    plan, where, _status = await _recorded_plan(version)
    if plan is None:
        return where or "No migration plan has been recorded yet — record it first."
    items = work_items(plan, feature_type, item_type)
    lines = [f"From {where}, the board would get {len(items)} {feature_type}(s) and "
             f"{sum(len(f['children']) for f in items)} {item_type}(s):", ""]
    for f in items:
        lines.append(f"- {feature_type}: **{f['title']}** — {f['description']}")
        lines += [f"  - {item_type}: {c['title']} — {c['description']}" for c in f["children"]]
    return "\n".join(lines)


async def _board(mode: str):
    """(connector, None) or (None, why-not). Writes also need the Consequential check AND an
    Architect or Project Admin role ON THIS PROJECT (permissions are a tenant-wide union)."""
    try:
        from config.connectors.context import get_connector  # noqa: PLC0415

        conn = get_connector()
    except Exception:  # noqa: BLE001
        return None, ("No board is connected to this stage. A Project Admin can wire Azure DevOps or Jira to the "
                      "Migration Strategy stage in project settings.")
    level = getattr(conn, "access_level", "__unscoped__")
    if level != "__unscoped__":
        from shared.authz.connector_access import label, permits  # noqa: PLC0415

        if not permits(level, mode):
            return None, f"{conn.display_name} is {label(level)} for this stage, so it cannot be used to {mode} board items."
    if mode == "write":
        from config.ws_helper import get_orchestrator_run, get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415
        from shared.authz.consequential import authorize_consequential  # noqa: PLC0415

        if not get_orchestrator_run():
            from shared.db import get_db_session_for_tenant  # noqa: PLC0415
            from shared.services.fallback_approval import project_roles  # noqa: PLC0415

            try:
                async with get_db_session_for_tenant(str(get_tenant_id())) as db:
                    roles = await project_roles(db, tenant_id=str(get_tenant_id()), project_id=str(get_project_id()),
                                                user_id=str(get_user_id()))
            except Exception:  # noqa: BLE001 — cannot prove the role ⇒ refuse
                roles = set()
            if not roles & {"architect", "project_admin"}:
                return None, ("Only an Architect or a Project Admin of this project writes the migration plan to the "
                              "board. Ask one of them to confirm it.")
        ok, why = await authorize_consequential(
            STAGE, action="Writing the migration waves to the project board",
            ask="show the user exactly the Features and items you are about to create (preview them) and ask.")
        if not ok:
            return None, why
    return conn, None


@tool
async def list_board_projects() -> str:
    """List the projects on the board connected to this stage."""
    conn, err = await _board("read")
    if err:
        return err
    try:
        projects = await conn.read_adapter("list_projects")
    except Exception as exc:  # noqa: BLE001
        return f"Error fetching projects: {type(exc).__name__}"
    if not projects:
        return "No projects found."
    return f"Projects on {conn.display_name}:\n" + "\n".join(
        f"- {p.get('name', '')}" + (f" ({p.get('key')})" if p.get("key") else "") for p in projects)


@tool
async def create_wave_work_items(project: str, version: int = 0, feature_type: str = "Feature",
                                 item_type: str = "User Story") -> str:
    """Write the RECORDED plan to the board: one Feature per wave, one item per module. CONSEQUENTIAL:
    preview it, show the user, and call this only after they say yes on this turn.

    Args:
        project: the board project name.
        version: the plan version (0 = the newest) — the same one you previewed.
        feature_type / item_type: as previewed.
    """
    conn, err = await _board("write")
    if err:
        return err
    plan, where, status = await _recorded_plan(version)
    if plan is None:
        return where or "No migration plan has been recorded yet — record it first."
    if status in ("rejected", "superseded"):
        return (f"Not written: {where} was {status}, so it is not the plan to put on the board. Write the approved "
                "plan (or the newest draft) — name its version.")
    lines = [f"Writing {where} to {conn.display_name} / {project}:"]
    for f in work_items(plan, feature_type, item_type):
        try:
            made = await conn.write_adapter("create_item", project=project, item_type=f["type"], title=f["title"],
                                            description=f["description"], acceptance_criteria="", parent_id="")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"- FAILED {f['type']} '{f['title']}': {type(exc).__name__}: {str(exc)[:160]}")
            continue
        fid = str(made.get("work_item_id") or made.get("id") or "")
        lines.append(f"- Created {f['type']} #{fid}: {f['title']}")
        for c in f["children"]:
            try:
                child = await conn.write_adapter("create_item", project=project, item_type=c["type"], title=c["title"],
                                                 description=c["description"], acceptance_criteria="", parent_id=fid)
                lines.append(f"  - Created {c['type']} #{child.get('work_item_id') or child.get('id', '?')}: {c['title']}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  - FAILED {c['type']} '{c['title']}': {type(exc).__name__}")
    return "\n".join(lines)


TOOLS = [
    read_migration_brief,
    read_assessment,
    read_target_design,
    propose_wave_order,
    check_calendar,
    estimate_effort,
    record_migration_strategy,
    export_strategy_document,
    preview_wave_work_items,
    list_board_projects,
    create_wave_work_items,
]
