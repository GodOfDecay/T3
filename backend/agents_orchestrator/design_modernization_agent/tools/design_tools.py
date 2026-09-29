"""Tools of the Target Architecture agent (Track 3, Phase E).

  read      the brief and the assessment THIS TURN pinned (`versions.turn_built_from`, noted by
            `standalone.upstream_from_pages` as it read them): the page's approved version, or —
            where the project does not enforce publication — its newest draft, labelled so. In
            an Orchestrator conversation, the conversation's own brief and assessment (its run),
            which is self-contained like everything the Orchestrator records.
  capture   the legacy system's interfaces, read from the pulled checkout by a deterministic scan
            (`analysis/interfaces.py`) — where the frozen contracts come from.
  record    the design: validated as the hand-over packet (`DesignPayload`), then against the
            brief, the pinned assessment and the code (`analysis/checks.py`); refused in words
            when it cannot be handed to Migration Strategy; otherwise stored on the run, frozen as
            the next version, and returned as the document.
  export    the recorded design as Word, PDF or Markdown, filed as a draft of this stage.

The ledger is NOT written here. Recording is producing; the ledger moves on APPROVAL (the
publish route calls `modernization_ledger.design_approved`), so an unapproved design never puts
a module into `designed`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import ValidationError

logger = logging.getLogger(__name__)

STAGE = "design_modernization"
FILE_SEGMENT = "design_modernization_agent"
BRIEF_STAGE, ASSESSMENT_STAGE = "requirements_modernization", "discovery"

#: The last design recorded in each conversation, for export. Keyed by session id.
_LAST_DESIGN: dict[str, dict] = {}
#: (checkout path, commit, modules) → inventory. The scan is deterministic for a commit.
_INVENTORY: dict[tuple, dict] = {}
_INVENTORY_CAP = 32
_SHOWN_PROBLEMS = 12


def _session_key() -> str:
    from config.ws_helper import get_session_id  # noqa: PLC0415

    return str(get_session_id() or "default")


# ── the inputs ───────────────────────────────────────────────────────────────


@dataclass
class Input:
    """One upstream artifact as this turn read it."""

    stage: str
    stored: Optional[dict] = None      # the stored brief / assessment
    version: Optional[int] = None      # None in an Orchestrator conversation
    status: str = "draft"              # the version store's vocabulary; "granted" = by exception
    packet: Optional[dict] = None      # the validated hand-over payload
    problems: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        noun = "brief" if self.stage == BRIEF_STAGE else "assessment"
        if self.version is None:
            return f"the {noun} recorded in this conversation"
        state = {"published": "approved", "granted": "approved by exception"}.get(self.status, "not yet approved")
        return f"{noun} v{self.version} ({state})"


async def _read_inputs() -> dict[str, Input]:
    from agents_orchestrator.modernization_common.handover.emit import (  # noqa: PLC0415
        assessment_packet, brief_packet, envelope_of,
    )
    from config.ws_helper import get_orchestrator_run, get_project_id, get_run_id, get_tenant_id  # noqa: PLC0415

    out = {BRIEF_STAGE: Input(BRIEF_STAGE), ASSESSMENT_STAGE: Input(ASSESSMENT_STAGE)}
    builders = {BRIEF_STAGE: brief_packet, ASSESSMENT_STAGE: assessment_packet}
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

                    row = (await db.execute(select(Run.migration_intent_payload, Run.discovery_artifacts)
                                            .where(Run.id == str(run_id)))).first()
                    if row is not None:
                        for stage, stored in ((BRIEF_STAGE, row[0]), (ASSESSMENT_STAGE, row[1])):
                            if stored:
                                out[stage].stored = stored
                                built = builders[stage](stored, {"version": 1, "status": "draft"})
                                out[stage].packet = built.packet.payload.model_dump(mode="json", by_alias=True) if built.ok else None
                                out[stage].problems = built.problems
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
                item.stored, item.version = row.payload, row.version
                item.status = "granted" if pin.get("status") == "granted" else row.status
                built = builders[stage](row.payload, envelope_of(row))
                item.packet = built.packet.payload.model_dump(mode="json", by_alias=True) if built.ok else None
                item.problems = built.problems
    except Exception:  # noqa: BLE001 — said to the agent, never taken as "nothing recorded"
        logger.exception("target architecture: reading the brief and assessment failed (project %s)", project_id)
        for item in out.values():
            item.problems = ["It could not be read just now (a database error). Try again."]
    return out


def _missing(item: Input) -> str:
    noun = "migration-intent brief" if item.stage == BRIEF_STAGE else "Dependency and Risk assessment"
    page = "Migration Intent" if item.stage == BRIEF_STAGE else "Dependency and Risk"
    if item.problems and item.stored:
        return (f"The {item.label} cannot be designed from: " + " ".join(item.problems[:5])
                + f" It is fixed on the {page} page.")
    if item.problems:
        return f"The {noun} could not be read: {item.problems[0]}"
    return (f"There is no {noun} to design from yet (or the project only builds on approved work and none is "
            f"approved). It is made on the {page} page, and approved there.")


# ── reading ──────────────────────────────────────────────────────────────────


@tool
async def read_migration_brief() -> str:
    """The migration-intent brief this design builds on: why, scope, constraints, the recommended
    target, the success measures, and MUST NOT CHANGE in the user's own words. Call it first."""
    from agents_orchestrator.requirements_modernization_agent.brief import brief_markdown  # noqa: PLC0415
    from shared.models.artifacts import MigrationIntentArtifact  # noqa: PLC0415

    item = (await _read_inputs())[BRIEF_STAGE]
    if not item.stored:
        return _missing(item)
    try:
        body = brief_markdown(MigrationIntentArtifact(**item.stored))
    except Exception:  # noqa: BLE001 — an older shape: the packet still says what matters
        body = json.dumps(item.packet or item.stored, indent=1, default=str)[:12_000]
    head = f"_This is {item.label}._"
    if item.packet is None:
        head += "\n\n" + _missing(item)
    elif item.packet.get("must_not_change"):
        head += ("\n\nMust not change (each becomes a frozen contract with brief_item set to exactly these words): "
                 + "; ".join(f"“{w}”" for w in item.packet["must_not_change"]))
    return f"{head}\n\n{body}"


def _assessment_table(packet: dict) -> str:
    lines = ["| Id | Module | Path | Tier | Score | Runtime | Fan-in | Blockers |", "|---|---|---|---|---:|---|---:|---|"]
    for m in packet.get("modules") or []:
        rt = m.get("runtime") or {}
        runtime = " ".join(x for x in (rt.get("name"), rt.get("version")) if x) or "not declared"
        lines.append(f"| {m['id']} | {m['name']} | `{m['path']}` | {m['tier']} | {m['score']} | "
                     f"{runtime} ({rt.get('status', 'unknown')}) | {m.get('fan_in') if m.get('fan_in') is not None else '—'} | "
                     f"{', '.join(m.get('blockers') or []) or '—'} |")
    return "\n".join(lines)


@tool
async def read_assessment() -> str:
    """The Dependency and Risk assessment this design builds on: every module with its id, path,
    tier, score and runtime; the dependency graph; end-of-life, deprecated and vulnerable flags;
    and the questions the code could not answer. Its ids, tiers and scores are fixed — cite them
    exactly. Call it first."""
    item = (await _read_inputs())[ASSESSMENT_STAGE]
    if not item.stored:
        return _missing(item)
    if item.packet is None:
        return f"_This is {item.label}._\n\n" + _missing(item)
    p = item.packet
    graph = ", ".join(f"{a}→{b}" for a, b in p.get("graph") or []) or "no module depends on another"
    flags = p.get("flags") or {}
    lines = [f"_This is {item.label}; repository {p.get('repository')}, commit `{str(p.get('commit'))[:10]}`._",
             "", "## Modules", "", _assessment_table(p), "", f"Dependencies (dependent→dependency): {graph}.", ""]
    for key, label in (("eol", "End-of-life"), ("deprecated", "Deprecated"), ("vulnerable", "Vulnerable")):
        lines.append(f"- {label}: {', '.join(flags.get(key) or []) or 'none'}")
    scanners = (item.stored or {}).get("scanners") or {}
    if scanners.get("trivy") not in (None, "ok"):
        lines.append("- Vulnerabilities were NOT scanned for this assessment — not measured, not zero.")
    questions = p.get("not_assessable_statically") or []
    if questions:
        lines += ["", "## Not assessable statically — ask these; never assume them", ""]
        lines += [f"- {q}" for q in questions]
    return "\n".join(lines)


@tool
async def get_module_detail(module: str) -> str:
    """Everything the assessment knows about one module: runtime, each dependency with its status,
    what it depends on and what depends on it, and each risk factor.

    Args:
        module: The module's id (M-03) or its name.
    """
    item = (await _read_inputs())[ASSESSMENT_STAGE]
    if not item.stored:
        return _missing(item)
    wanted = (module or "").strip().lower()
    modules = item.stored.get("modules") or []
    match = next((m for m in modules if wanted in (str(m.get("name", "")).lower(), str(m.get("id") or "").lower())), None)
    if match is None:
        return f"No module '{module}'. Modules: " + ", ".join(f"{m.get('id') or '?'} {m.get('name')}" for m in modules)
    return json.dumps(match, indent=1, default=str)[:15_000]


@tool
async def get_dependency_graph(module: str = "") -> str:
    """The assessment's dependency graph as edges. With `module` (its name), only that module's."""
    item = (await _read_inputs())[ASSESSMENT_STAGE]
    if not item.stored:
        return _missing(item)
    edges = ((item.stored.get("dependency_graph") or {}).get("edges")) or []
    if module:
        node = f"module:{module.strip()}".lower()
        edges = [e for e in edges if node in (str(e.get("from", "")).lower(), str(e.get("to", "")).lower())]
    lines = [f"{e.get('from')} -> {e.get('to')} ({e.get('type')}{', ' + e['version'] if e.get('version') else ''})"
             for e in edges[:400]]
    return "\n".join(lines) if lines else "No edges."


# ── the legacy interfaces ────────────────────────────────────────────────────


def _checkout() -> tuple[Optional[Path], Optional[dict]]:
    from agents_orchestrator.modernization_common.legacy_code import (  # noqa: PLC0415
        checkout_dir, current_pull, current_scope,
    )

    project_id, run_id = current_scope()
    pull = current_pull(project_id, run_id) if project_id else None
    return (checkout_dir(project_id, run_id), pull) if pull else (None, None)


def inventory_for(root: Path, commit: str, modules: list[dict]) -> dict:
    """The (cached) interface inventory of a checkout at a commit."""
    from agents_orchestrator.design_modernization_agent.analysis.interfaces import capture_interfaces  # noqa: PLC0415

    # The MODULES are part of the key: the same checkout attributed with the pull profile's names
    # and with an assessment's ids are two different inventories (review fix #5).
    key = (str(root), commit or "", tuple(sorted((str(m.get("id") or m.get("name") or ""), str(m.get("path") or ""))
                                                 for m in modules)))
    if key not in _INVENTORY:
        if len(_INVENTORY) >= _INVENTORY_CAP:
            _INVENTORY.clear()
        _INVENTORY[key] = capture_interfaces(root, modules, commit)
    return _INVENTORY[key]


def _module_refs(assessment: Input, pull: Optional[dict]) -> list[dict]:
    if assessment.packet:
        return [{"id": m["id"], "name": m["name"], "path": m["path"]} for m in assessment.packet["modules"]]
    return [{"name": m.get("name"), "path": m.get("path")} for m in ((pull or {}).get("profile") or {}).get("modules") or []]


def _commit_note(assessment: Input, pull: Optional[dict]) -> str:
    assessed = str((assessment.packet or {}).get("commit") or "")
    pulled = str((pull or {}).get("commit") or "")
    if assessed and pulled and not (assessed.startswith(pulled[:7]) or pulled.startswith(assessed[:7])):
        return (f"The pulled code is at commit {pulled[:10]}, but the assessment was made at {assessed[:10]}. "
                "Module ids and paths are only stable within one commit: say so, and suggest re-running the "
                "assessment on this commit before recording.")
    return ""


@tool
async def capture_legacy_interfaces() -> str:
    """List what the legacy system exposes and consumes, read from the pulled code: HTTP endpoints
    and pages, outbound calls, files it writes and reads, scheduled jobs, database tables, queues —
    each with its file:line. The frozen contracts come from here. Call it before designing."""
    from agents_orchestrator.design_modernization_agent.analysis.interfaces import interfaces_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.legacy_code import _no_code, current_scope  # noqa: PLC0415

    root, pull = _checkout()
    if root is None:
        return _no_code(*current_scope())
    assessment = (await _read_inputs())[ASSESSMENT_STAGE]
    inventory = await asyncio.to_thread(inventory_for, root, str(pull.get("commit") or ""), _module_refs(assessment, pull))
    note = _commit_note(assessment, pull)
    return interfaces_markdown(inventory) + (f"\n\n**{note}**" if note else "")


def _tree(root: Path) -> tuple[set[str], set[str]]:
    files, dirs = set(), set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        rel = Path(dirpath).relative_to(root).as_posix()
        if rel != ".":
            dirs.add(rel)
        for name in filenames:
            files.add(name if rel == "." else f"{rel}/{name}")
    return files, dirs


# ── recording ────────────────────────────────────────────────────────────────


def check_design(design, brief: dict, assessment: dict, assessment_version: Optional[int],
                 files: Optional[set[str]], dirs: Optional[set[str]], captured: Optional[set[str]],
                 as_of: date):
    """Every cross-artifact rule, in one place — (problems, notes). `design` is a validated
    `DesignPayload`; `brief` and `assessment` are hand-over payloads (dicts)."""
    from agents_orchestrator.design_modernization_agent.analysis import checks  # noqa: PLC0415

    d = design.model_dump(mode="json")
    problems: list[str] = []
    notes: list[str] = []
    problems += checks.check_modules(d["modules"], assessment, assessment_version)
    problems += checks.check_must_not_change(d["frozen_contracts"], brief.get("must_not_change") or [])
    located = checks.check_locations(d["frozen_contracts"], d["traps"], files, dirs, captured)
    problems += located.problems
    notes += located.notes
    targets = [(f"{layer['layer']} target", layer["target"]) for layer in d["layers"]]
    if d.get("data_migration"):
        targets.append(("Data migration target", d["data_migration"]["target"]))
    versions = checks.check_versions(targets, as_of)
    problems += versions.problems
    notes += versions.notes
    problems += checks.check_data_migration(d["layers"], d.get("data_migration"))
    problems += checks.check_diagrams(d["diagrams"])
    problems += checks.check_questions(assessment.get("not_assessable_statically") or [],
                                       d["resolved_questions"], d["open_questions"])
    return problems, notes


def _refusal(problems: list[str]) -> str:
    shown = problems[:_SHOWN_PROBLEMS]
    more = f"\n…and {len(problems) - len(shown)} more." if len(problems) > len(shown) else ""
    return ("NOT RECORDED YET — the design cannot be handed to Migration Strategy as it is:\n"
            + "\n".join(f"- {p}" for p in shown) + more
            + "\nFix these and record the whole design again. Where a fix needs the user (a question the "
              "code cannot answer, a contract they have not confirmed), ask them — at most three questions at a time.")


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the current target design."
    except Exception as exc:  # noqa: BLE001 — the user still gets the document
        logger.exception("target architecture: persisting the design failed")
        return f"Not saved ({type(exc).__name__}) — the design below is still complete."


@tool
async def record_target_design(design: dict) -> str:
    """Record the target design once the user agrees with it (or asks you to go ahead). Re-record
    the WHOLE design to revise it; the newest version wins.

    `design` is ONE JSON object:
    {
      "summary": "2-4 sentences",
      "layers": [{"layer": "2-4 words", "today": "tech · version", "target": "tech · exact version",
                  "modules": ["M-02"]}],
      "modules": [{"module_id": "M-02", "module": "name exactly as the assessment gives it",
                   "tier": "the assessment's", "risk_score": 56,
                   "patterns": ["in_place_upgrade" | "strangler_fig" | "branch_by_abstraction" |
                                "parallel_run" | "rewrite" | "replatform" | "retire" | "keep"],  (1 or 2)
                   "rationale": "cites tier, risk factors and coupling",
                   "adr_ids": ["ADR-03"], "contract_ids": ["CT-01"]}],       EVERY assessed module
      "interop": {"routing": "", "data": "", "shared_libraries": "", "jobs": "", "identity": ""},
      "ordering_constraints": ["what restricts the order of the move, and why (ADR-02)"],
      "frozen_contracts": [{"id": "CT-01", "name": "", "kind": "http|file|report|db|queue|event",
                            "legacy_location": "path[:line] from the interface inventory",
                            "consumers": [""], "proof": "how it is proven unchanged",
                            "status": "confirmed|proposed",
                            "brief_item": "the brief's must-not-change words, EXACTLY, or null"}],
      "data_migration": {"source": "", "target": "", "method": "", "behaviour_changes": [""],
                         "cutover": ""},                      required when the database changes
      "nfr": [{"measure": "", "target": "", "source": "brief|design"}],
      "security_design": [""],
      "traps": [{"id": "TR-01", "change": "", "affects": ["M-02"], "where": "path, folder or glob",
                 "effect": "", "contract_ids": ["CT-01"]}],
      "adrs": [{"id": "ADR-01", "title": "", "context": "", "options": ["", ""], "decision": "",
                "consequences": "", "modules": ["M-02"], "contracts": ["CT-01"]}],
      "diagrams": [{"title": "AS-IS container", "mermaid": "flowchart LR ..."},
                   {"title": "TRANSITION", "mermaid": "..."}, {"title": "TO-BE container", "mermaid": "..."}],
      "departures_from_brief": [{"brief_said": "", "design_says": "", "adr_id": "ADR-08"}],
      "resolved_questions": [{"question": "the assessment's question, verbatim", "answer": "",
                              "source": "user|document"}],
      "open_questions": [""]
    }
    It refuses — naming each problem — a module missing or cited under the wrong id, name, tier or
    score; a must-not-change item with no contract; a contract whose location is not in the code, or
    confirmed without naming one file the inventory (or the brief) backs; a trap that names no place
    in the code; code pulled at another commit than the assessment's; a .NET, Java, Node.js or Python
    target past (or within a year of) end of support, or "latest"; a changing database with
    no data migration; a missing AS-IS / TRANSITION / TO-BE diagram; an unanswered question from the
    assessment; an ADR with fewer than two options; an id cited but not defined.
    """
    from agents_orchestrator.modernization_common.handover.emit import _problems, design_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.handover.packets import DesignPayload  # noqa: PLC0415

    if not isinstance(design, dict):
        return "NOT RECORDED YET — `design` must be one JSON object (see the tool's description)."
    inputs = await _read_inputs()
    brief, assessment = inputs[BRIEF_STAGE], inputs[ASSESSMENT_STAGE]
    missing = [_missing(i) for i in (brief, assessment) if i.packet is None]
    if missing:
        return "NOT RECORDED — a target design is checked against the brief and the assessment:\n" + "\n".join(
            f"- {m}" for m in missing) + "\nTell the user what is needed; do not record a design without them."
    try:
        payload = DesignPayload.model_validate(design)
    except ValidationError as exc:
        return _refusal(_problems(exc))

    root, pull = _checkout()
    files = dirs = captured = None
    inventory = None
    if root is not None:
        files, dirs = await asyncio.to_thread(_tree, root)
        inventory = await asyncio.to_thread(inventory_for, root, str(pull.get("commit") or ""),
                                            _module_refs(assessment, pull))
        from agents_orchestrator.design_modernization_agent.analysis.interfaces import lines_by_file  # noqa: PLC0415

        captured = lines_by_file(inventory)
    problems, notes = check_design(payload, brief.packet, assessment.packet, assessment.version,
                                   files, dirs, captured, date.today())
    # Locations checked against code at ANOTHER commit than the assessment's prove nothing about
    # the assessed modules, so this is a refusal, not a note (review fix #12).
    commit_note = _commit_note(assessment, pull)
    if commit_note:
        problems.append(commit_note.replace("say so, and suggest", "ask the user to pull the assessed commit, or suggest"))
    if problems:
        return _refusal(problems)
    for item in (brief, assessment):
        if item.version is not None and item.status == "draft":
            notes.append(f"Built from {item.label}: the design is provisional until it is approved.")

    from agents_orchestrator.modernization_common.tech_stack import applied_stack, effective_stack  # noqa: PLC0415
    from shared.models.artifacts import TargetDesignArtifact  # noqa: PLC0415

    artifact = TargetDesignArtifact(
        **payload.model_dump(mode="json"),
        system_name=str((brief.packet or {}).get("system_name") or ""),
        sources={
            "brief": {"version": brief.version, "status": brief.status},
            "assessment": {"version": assessment.version, "status": assessment.status,
                           "commit": assessment.packet.get("commit"), "repository": assessment.packet.get("repository")},
            "checkout_commit": (pull or {}).get("commit"),
        },
        module_paths={m["id"]: m["path"] for m in assessment.packet["modules"]},
        interfaces=({"commit": inventory.get("commit"), "counts": inventory.get("counts"),
                     "total": inventory.get("total")} if inventory else None),
        tech_stack=applied_stack(await effective_stack(), None),
        notes=notes,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        agent_session_id=_session_key(),
    ).model_dump(mode="json")
    handover = design_packet(artifact, {"version": 1, "status": "draft"})
    if not handover.ok:  # the same model validated it above; a failure here is a bug, said plainly
        return _refusal(handover.problems)

    _LAST_DESIGN[_session_key()] = artifact
    saved = await _persist(artifact)
    from agents_orchestrator.design_modernization_agent.design_document import design_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415

    version = await freeze_version(STAGE, artifact)
    return f"{design_markdown(artifact)}\n\n_{saved_line(saved, version, 'target design')}_"


# ── exporting ────────────────────────────────────────────────────────────────


async def _latest_design() -> Optional[dict]:
    """On a page: the stage's NEWEST VERSION — what the page shows, including a restore made
    after this chat recorded (review fix #11). In an Orchestrator conversation: what it recorded."""
    from config.ws_helper import get_orchestrator_run, get_project_id, get_tenant_id  # noqa: PLC0415

    if get_orchestrator_run() or not (get_project_id() and get_tenant_id()):
        return _LAST_DESIGN.get(_session_key())
    try:
        from shared.db import get_db_session_for_tenant  # noqa: PLC0415
        from shared.services import artifact_versions as svc  # noqa: PLC0415

        async with get_db_session_for_tenant(str(get_tenant_id())) as db:
            row = await svc.latest_version(db, str(get_project_id()), STAGE)
        return row.payload if row is not None and row.payload else None
    except Exception:  # noqa: BLE001
        logger.exception("target architecture: reading the latest design failed")
        return None


@tool
async def export_target_design(filename: str = "target_architecture.docx") -> str:
    """Export the recorded target design as a document the Architect can put forward for sign-off.
    Format follows the extension: .docx, .pdf, .md."""
    design = await _latest_design()
    if design is None:
        return "No target design has been recorded yet — record it first."
    from agents_orchestrator.design_modernization_agent.design_document import design_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from shared.tools.doc_export import (  # noqa: PLC0415
        export_result_message, normalise_filename, render_document, supported_list,
    )

    name = normalise_filename(filename, "target_architecture.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(design_markdown(design), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(
        name, url,
        ["It is saved as a draft of the Target Architecture stage. The design VERSION on the page is what "
         "gets signed off — an Architect who did not produce it, or a Project Admin."],
    )


from agents_orchestrator.modernization_common.legacy_code import LEGACY_TOOLS  # noqa: E402
from agents_orchestrator.modernization_common.tech_stack import get_project_tech_stack  # noqa: E402

TOOLS = [
    read_migration_brief,
    read_assessment,
    get_module_detail,
    get_dependency_graph,
    capture_legacy_interfaces,
    get_project_tech_stack,
    record_target_design,
    export_target_design,
    *LEGACY_TOOLS,
]
