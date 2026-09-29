"""Agents 1 and 2 emit their hand-over packets (Phase D).

The Migration Intent brief and the Dependency and Risk assessment are stored in their own,
richer shapes (`MigrationIntentArtifact`, the assessment dict). What Target Architecture
reads is the PACKET (`packets.BriefPacket`, `packets.AssessmentPacket`): the envelope from the
frozen version row, and the payload mapped from the stored artifact. Building it validates it,
so a brief or assessment that could not be handed over says why — in words the record tool
passes back to the agent (research §5.8 rule 5), and that the page shows beside the version.

    brief_packet(payload, envelope)       -> Emitted
    assessment_packet(payload, envelope)  -> Emitted
    design_packet(payload, envelope)      -> Emitted   (Phase E: Target Architecture → Strategy)
    envelope_of(row)                      the envelope fields from an `artifact_versions` row

WHAT IS MAPPED, AND WHAT IS NOT INVENTED. A field the stored artifact does not have stays
empty; it is never filled with a guess. A deadline written as prose ("Q3 2027") has no date,
so the packet carries it under constraints in the user's words rather than dropping it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from .packets import AssessmentPacket, BriefPacket

#: Stage → the envelope's artifact name (`packets.ArtifactName`).
STAGE_ARTIFACT = {
    "requirements_modernization": "migration_intent_payload",
    "discovery": "discovery_artifacts",
    "design_modernization": "target_design_artifacts",
    "strategy": "strategy_artifacts",
    "testing_modernization": "equivalence_artifacts",
    "development_modernization": "migration_artifacts",
    "code_review_modernization": "migration_review_artifacts",
    "security_modernization": "modernization_security_artifacts",
    "deployment_modernization": "cutover_artifacts",
    "documentation_modernization": "cutover_pack_artifacts",
}

_OWNER_ROLE = re.compile(r"(?i)\b(business owner|product owner|sponsor)\b")


@dataclass
class Emitted:
    """A packet, or the reasons there is none. Never both."""

    packet: Optional[BaseModel] = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.packet is not None

    def as_dict(self) -> dict:
        return {"ok": self.ok, "problems": self.problems,
                "packet": self.packet.model_dump(mode="json", by_alias=True) if self.packet else None}


#: Plain words for the problems a person can fix — shown on the page and passed to the agent.
_PLAIN = {
    "goal": "The goal is missing.",
    "system_name": "The system is not named.",
    "target_stack": "No target stack is recorded.",
    "scope.in": "Nothing is recorded as in scope.",
    "success_measures": "There is no measurable success measure.",
    "repository": "The repository is not recorded.",
    "commit": "The assessed commit is not recorded.",
    "modules": "No modules were assessed.",
}
_MEASURE_FIELD = re.compile(r"^success_measures\.(\d+)\.(kind|metric|target)$")


def _plain(where: str, msg: str) -> str:
    m = _MEASURE_FIELD.match(where)
    if m:
        n, field = int(m.group(1)) + 1, m.group(2)
        if field == "kind":
            return (f"Success measure {n} has no kind (equivalence, performance, security, schedule or "
                    "cost).")
        return f"Success measure {n} has no {field}."
    if where in _PLAIN:
        return _PLAIN[where]
    return f"{where}: {msg}" if where else msg


def _problems(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err.get("loc", ()) if p != "payload")
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        line = _plain(where, msg)
        if line not in out:
            out.append(line)
    return out


def _numeric_id(value: Any) -> tuple[int, str]:
    digits = re.sub(r"\D", "", str(value or ""))
    return (int(digits) if digits else 0, str(value))


def _build(model: type[BaseModel], data: dict) -> Emitted:
    try:
        return Emitted(packet=model.model_validate(data))
    except ValidationError as exc:
        return Emitted(problems=_problems(exc))


def envelope_of(row: Any) -> dict:
    """The envelope fields from a frozen version row — never assembled by a model. THE ONE
    implementation (the unused Phase C copy in `version_lineage` was removed: two builders that
    disagreed on a grant pin). A read by consumption grant was of an unpublished version, so its
    pin says `draft` — what the input actually was."""
    built_from = []
    for pin in getattr(row, "built_from", None) or []:
        artifact = pin.get("artifact") or STAGE_ARTIFACT.get(pin.get("stage") or "")
        status = pin.get("status")
        built_from.append({"artifact": artifact, "version": pin.get("version"),
                           "status": "draft" if status in (None, "granted") else status})
    created = getattr(row, "created_at", None)
    return {"version": row.version, "status": row.status, "built_from": built_from,
            "produced_by": {"user_id": getattr(row, "produced_by", None),
                            "run_id": str(row.run_id) if getattr(row, "run_id", None) else None},
            "produced_at": created.isoformat() if created else None}


# ── 1. the brief ─────────────────────────────────────────────────────────────

def _iso_date(value: str) -> Optional[str]:
    value = (value or "").strip()
    try:
        return date.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def brief_payload(brief: dict) -> dict:
    """The packet's payload, mapped from a stored `MigrationIntentArtifact` (as a dict)."""
    target = ((brief.get("target_state") or {}).get("stack") or "").strip()
    deadline = brief.get("deadline") or ""
    constraints = list(brief.get("constraints") or [])
    if deadline and not _iso_date(deadline):
        constraints.append(f"Deadline: {deadline}")
    owner = next((s.get("name") for s in brief.get("stakeholders") or []
                  if _OWNER_ROLE.search(s.get("role") or "")), None)
    return {
        "system_name": brief.get("system_name") or "",
        "goal": brief.get("goal") or "",
        "target_stack": [target] if target else [],
        "scope": {"in": list(brief.get("in_scope") or []), "out": list(brief.get("out_of_scope") or [])},
        "constraints": constraints,
        "deadline": _iso_date(deadline),
        "budget": brief.get("budget") or None,
        "must_not_change": list(brief.get("must_not_change") or []),
        "success_measures": [
            {"metric": m.get("metric") or "", "today": m.get("current") or None,
             "target": m.get("target") or "", "kind": m.get("kind")}
            for m in brief.get("success_measures") or []
        ],
        "business_owner": owner,
        "open_questions": list(brief.get("open_questions") or []),
    }


def brief_packet(brief: dict, envelope: dict) -> Emitted:
    return _build(BriefPacket, {**envelope, "payload": brief_payload(brief)})


# ── 2. the assessment ────────────────────────────────────────────────────────

_RUNTIME_STATUSES = {"eol", "approaching", "legacy", "supported", "unknown"}


def assessment_payload(assessment: dict) -> dict:
    """The packet's payload, mapped from a stored assessment (schema v2: modules carry `id`)."""
    rows = assessment.get("modules") or []
    id_of = {r.get("name"): r.get("id") for r in rows}
    modules, graph = [], []
    flagged: dict[str, set[str]] = {}
    for kind, items in (assessment.get("flags") or {}).items():
        for item in items or []:
            flagged.setdefault(item.get("module") or "", set()).add(kind)
    for r in sorted(rows, key=lambda r: _numeric_id(r.get("id"))):
        runtime = r.get("runtime") or {}
        modules.append({
            "id": r.get("id"), "name": r.get("name"), "path": r.get("path"),
            "tier": (r.get("risk") or {}).get("tier"), "score": (r.get("risk") or {}).get("score"),
            "runtime": ({"name": runtime.get("name"), "version": runtime.get("version") or None,
                         "status": runtime.get("status") if runtime.get("status") in _RUNTIME_STATUSES else "unknown",
                         "eol_date": runtime.get("eol_date")} if runtime.get("name") else None),
            "loc": r.get("loc"), "fan_in": len(r.get("dependents") or []),
            "flags": sorted(flagged.get(r.get("name") or "", set())), "blockers": list(r.get("blockers") or []),
        })
        for dependency in r.get("depends_on") or []:
            if dependency in id_of:
                graph.append((r.get("id"), id_of[dependency]))
    flags = {kind: sorted({id_of.get(i.get("module"), i.get("module")) for i in items or []})
             for kind, items in (assessment.get("flags") or {}).items() if kind in ("eol", "deprecated", "vulnerable")}
    repo = assessment.get("repository") or {}
    golden = assessment.get("golden_master") or {}
    return {
        "repository": repo.get("url") or repo.get("name") or "",
        "commit": repo.get("commit") or "",
        "modules": modules,
        "graph": sorted(set(graph)),
        "flags": flags,
        "golden_master": {"status": golden.get("status") or "not_captured",
                          "baselines": list(golden.get("baselines") or [])},
        "not_assessable_statically": [i.get("question") for i in assessment.get("not_assessable_statically") or []
                                      if i.get("question")],
    }


def design_payload(design: dict) -> dict:
    """The packet's payload from a stored target design (`TargetDesignArtifact` as a dict): the
    design fields only — sources, paths and notes are the page's, not the hand-over's."""
    from .packets import DesignPayload  # noqa: PLC0415

    return {name: design[name] for name in DesignPayload.model_fields if name in design}


def design_packet(design: dict, envelope: dict) -> Emitted:
    from .packets import DesignPacket  # noqa: PLC0415

    return _build(DesignPacket, {**envelope, "payload": design_payload(design)})


def assessment_packet(assessment: dict, envelope: dict) -> Emitted:
    if any(not (m or {}).get("id") for m in assessment.get("modules") or []):
        # Schema 1 (or a restored copy of one): no module ids, so nothing downstream can cite a
        # module. One sentence with the remedy, not one validation error per module and edge.
        return Emitted(problems=["This assessment was made before modules had ids (M-01, …). Run the "
                                 "assessment again to hand it to Target Architecture."])
    return _build(AssessmentPacket, {**envelope, "payload": assessment_payload(assessment)})
