"""Typed Pydantic artifact models for SDLC pipeline stages (M2-02, D-11).

ORM artifact models — map 1:1 to JSONB columns on the runs table:
    RequirementsArtifact  -> runs.requirements_payload
    DesignArtifact        -> runs.design_artifacts
    DevelopmentArtifact   -> runs.development_artifacts
    TestingArtifact       -> runs.testing_artifacts
    CodeReviewArtifact    -> runs.code_review_artifacts
    SecurityArtifact      -> runs.security_artifacts
model_dump() output is the only accepted input for those JSONB columns —
unvalidated dicts may not be written directly (T-M2-02-02 mitigation).

Utilities:
    TraceLink             — bidirectional traceability link between artifact items
    validate_handoff()    — consumer-side helper; strips sentinels + validates any BaseModel
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator


class RequirementsArtifact(BaseModel):
    agent_session_id: str
    brd_content: Optional[str] = None
    user_stories: Optional[List[dict]] = None
    acceptance_criteria: Optional[List[str]] = None
    risk_register: Optional[List[dict]] = None
    version: int = 1


class PlanArtifact(BaseModel):
    """The PM agent's output: what the work is, when it happens, and who does it.

    A BASELINE FROM THE FIRST SAVE. Answering "how far have we slipped" needs what was
    originally committed to, and a baseline added after plans already exist leaves every
    earlier plan with no history to compare against. It costs one field now and cannot
    be retrofitted later.

    Every field is optional because a plan is built up over a conversation — a work
    breakdown with no schedule yet is a legitimate intermediate state, not an invalid
    one.
    """

    agent_session_id: str = ""
    #: Work items with estimates, in the canonical board-item shape.
    tasks: Optional[List[dict]] = None
    #: Sprints or dated phases, each with its items.
    schedule: Optional[List[dict]] = None
    #: Who is on what, against real capacity where the board exposes it (ADO does,
    #: Jira does not — see the connector manifests).
    assignments: Optional[List[dict]] = None
    #: Blockers and cross-team dependencies, with what each one threatens.
    risks: Optional[List[dict]] = None
    milestones: Optional[List[dict]] = None
    #: The first committed version of `schedule`, kept unchanged for comparison.
    baseline: Optional[dict] = None
    #: Board and provider the plan was built against, so a later re-plan knows where
    #: the items live without asking again.
    board_project: Optional[str] = None
    provider_kind: Optional[str] = None
    version: int = 1


class DesignArtifact(BaseModel):
    hld: Optional[str] = None
    lld: Optional[str] = None
    api_contracts: Optional[str] = None
    database_schema: Optional[str] = None
    c4_diagram_url: Optional[str] = None
    adrs: Optional[List[dict]] = None
    security_checklist: Optional[str] = None
    version: int = 1


class DevelopmentArtifact(BaseModel):
    repo_url: Optional[str] = None
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    code_summary: Optional[str] = None
    test_results: Optional[dict] = None
    version: int = 1


class TestingArtifact(BaseModel):
    test_plan: Optional[str] = None
    test_cases: Optional[List[dict]] = None
    coverage_report: Optional[dict] = None
    defect_log: Optional[List[dict]] = None
    version: int = 1


class CodeReviewArtifact(BaseModel):
    pr_ref: Optional[str] = None
    findings: List[dict] = []
    requirements_coverage: Optional[dict] = None
    design_conformance: Optional[dict] = None
    merge_recommendation: Optional[str] = None
    review_summary: Optional[str] = None
    semgrep_results: Optional[List[dict]] = None
    version: int = 1


class SecurityArtifact(BaseModel):
    scope: Optional[str] = None
    dependency_findings: List[dict] = []
    code_findings: List[dict] = []
    secret_findings: List[dict] = []
    risk_score: Optional[str] = None
    remediation_plan: List[dict] = []
    security_sign_off: bool = False
    scan_summary: Optional[str] = None
    version: int = 1


# ---------------------------------------------------------------------------
# Track 3 (Code Modernization) — its own portfolio, its own columns
# ---------------------------------------------------------------------------


class StackState(BaseModel):
    """One end of a migration: what the system runs on."""

    stack: str = ""
    description: str = ""


class Stakeholder(BaseModel):
    name: str
    role: str = ""


class LegacyRepository(BaseModel):
    """Where the legacy code lives — what the Dependency and Risk agent will clone."""

    provider: str = ""
    project: str = ""
    name: str = ""
    url: str = ""


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _pick(value: Any, allowed: Dict[str, str], default: str) -> str:
    """Normalise a free-text label onto one of `allowed` ("Re-platform" -> replatform)."""
    slug = _slug(value)
    if not slug:
        return default
    if slug in allowed:
        return allowed[slug]
    for key, label in allowed.items():
        if slug.startswith(key):
            return label
    for key, label in allowed.items():  # "soc_2_compliance_deadline" -> compliance
        if len(key) >= 4 and key in slug:
            return label
    return default


#: Why a modernization happens — the categories the brief colours and groups by.
DRIVER_CATEGORIES = {
    "end_of_support": "end_of_support", "end_of_life": "end_of_support", "eol": "end_of_support",
    "support": "end_of_support", "security": "security", "vulnerab": "security",
    "cost": "cost", "hosting": "cost", "licen": "cost", "skills": "skills", "skill": "skills",
    "hiring": "skills", "talent": "skills", "compliance": "compliance", "regulat": "compliance",
    "audit": "compliance", "performance": "performance", "scal": "performance", "other": "other",
}
#: What happens to a part of the system.
CHANGE_TYPES = {
    "upgrade": "upgrade", "update": "upgrade", "rewrite": "rewrite", "rebuild": "rewrite",
    "re_write": "rewrite", "replatform": "replatform", "re_platform": "replatform",
    "rehost": "replatform", "re_host": "replatform", "migrate": "replatform",
    "lift_and_shift": "replatform", "containeri": "replatform",
    "replace": "replace", "retire": "retire", "decommission": "retire", "keep": "keep",
    "retain": "keep", "new": "new", "add": "new",
}
#: Support status of today's technology (the same words Discovery uses).
SUPPORT_STATUSES = {
    "eol": "eol", "end_of_life": "eol", "unsupported": "eol", "approaching": "approaching",
    "support_ending": "approaching", "legacy": "legacy", "supported": "supported",
    "unknown": "unknown",
}
EFFORT_LEVELS = {"low": "low", "small": "low", "s": "low", "medium": "medium", "m": "medium",
                 "moderate": "medium", "high": "high", "large": "high", "l": "high"}
MILESTONE_KINDS = {
    "freeze": "freeze", "compliance": "compliance", "audit": "compliance", "deadline": "deadline",
    "exit": "deadline", "cutover": "cutover", "go_live": "cutover", "golive": "cutover",
    "decommission": "decommission", "retire": "decommission", "start": "start", "other": "other",
}


class BusinessDriver(BaseModel):
    """One reason the modernization is happening, tagged so the brief can group it."""

    category: str = "other"
    title: str = ""
    detail: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v: Any) -> str:
        return _pick(v, DRIVER_CATEGORIES, "other")


class LayerChange(BaseModel):
    """One row of "the change at a glance": a part of the system, today and target."""

    layer: str
    current: str = ""
    current_status: str = ""
    target: str = ""
    change_type: str = ""
    modules: List[str] = []

    @field_validator("current_status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> str:
        return _pick(v, SUPPORT_STATUSES, "") if v else ""

    @field_validator("change_type", mode="before")
    @classmethod
    def _change(cls, v: Any) -> str:
        return _pick(v, CHANGE_TYPES, "") if v else ""


class Alternative(BaseModel):
    option: str
    why_not: str = ""


class Recommendation(BaseModel):
    """The target stack as the agent recommends it — labelled as a recommendation, and
    accepted when the BA signs the brief off."""

    summary: str = ""
    recommended_by: str = "agent"
    rationale: List[str] = []
    alternatives: List[Alternative] = []

    @field_validator("recommended_by", mode="before")
    @classmethod
    def _by(cls, v: Any) -> str:
        return "user" if _slug(v) in {"user", "customer", "business", "ba"} else "agent"


class ModuleChange(BaseModel):
    """What happens to one module of the legacy code."""

    module: str
    path: str = ""
    current: str = ""
    current_status: str = ""
    target: str = ""
    change_type: str = ""
    changes: List[str] = []
    effort: str = ""

    @field_validator("current_status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> str:
        return _pick(v, SUPPORT_STATUSES, "") if v else ""

    @field_validator("change_type", mode="before")
    @classmethod
    def _change(cls, v: Any) -> str:
        return _pick(v, CHANGE_TYPES, "") if v else ""

    @field_validator("effort", mode="before")
    @classmethod
    def _effort(cls, v: Any) -> str:
        return _pick(v, EFFORT_LEVELS, "") if v else ""


class TradeOff(BaseModel):
    decision: str
    gain: str = ""
    cost: str = ""


class Milestone(BaseModel):
    date: str
    label: str
    kind: str = "other"

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> str:
        return _pick(v, MILESTONE_KINDS, "other")


#: What a success measure is about (research §6.1). Migration Strategy turns the
#: `equivalence` and `performance` ones into equivalence criteria without parsing text.
MEASURE_KINDS = ("equivalence", "performance", "security", "schedule", "cost")


class SuccessMeasure(BaseModel):
    """A measurable success criterion: the metric, where it is today, where it must be, and
    what KIND of measure it is. `kind` is None on a brief recorded before it existed; the
    record tool requires it on every new one (the hand-over packet does)."""

    metric: str
    current: str = ""
    target: str = ""
    kind: Optional[str] = None

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Optional[str]:
        value = str(v or "").strip().lower()
        return value if value in MEASURE_KINDS else None


class MigrationIntentArtifact(BaseModel):
    """-> runs.migration_intent_payload. The Track 3 Requirements agent's brief:
    why the modernization is happening, what the system is today, the target the agent
    recommends (or the user named), what changes in each module and the trade-offs,
    scope, constraints, milestones and how success is measured. Not a story backlog —
    Track 3 has no INVEST stories.

    Version 2 added the structured sections (goal, tagged drivers, the change per layer
    and per module, the recommendation, trade-offs, milestones, measures). Every one of
    them defaults to empty, so a version-1 brief still loads and still renders."""

    system_name: str = ""
    goal: str = ""
    business_drivers: List[str] = []
    drivers: List[BusinessDriver] = []
    current_state: StackState = StackState()
    target_state: StackState = StackState()
    layers: List[LayerChange] = []
    recommendation: Optional[Recommendation] = None
    module_changes: List[ModuleChange] = []
    trade_offs: List[TradeOff] = []
    in_scope: List[str] = []
    out_of_scope: List[str] = []
    constraints: List[str] = []
    # Interfaces, files and reports the user said must not change, IN THE USER'S WORDS
    # (the record tool checks each against the conversation). Target Architecture turns
    # each into a contract (CT-xx) that later agents prove unchanged. Research §6.1.
    must_not_change: List[str] = []
    # Whether the entries were checked against the conversation: True (checked), False (the
    # conversation could not be read, so they were NOT checked — the brief must say so rather
    # than claim "the user's own words"), None (nothing to check, or recorded before Phase D).
    must_not_change_verified: Optional[bool] = None
    deadline: str = ""
    budget: str = ""
    # Phase F (universal planning inputs): when a cutover may take the system down and for how
    # long ("Sunday nights, at most 2 hours"), and where the data must stay ("EU regions only").
    # In the user's words; empty when they gave none. The change freeze is a `freeze` milestone.
    downtime_window: str = ""
    data_residency: str = ""
    milestones: List[Milestone] = []
    success_criteria: List[str] = []
    success_measures: List[SuccessMeasure] = []
    stakeholders: List[Stakeholder] = []
    assumptions: List[str] = []
    risks: List[str] = []
    open_questions: List[str] = []
    legacy_repository: Optional[LegacyRepository] = None
    # The Agent Studio stack in force when the brief was recorded — set by the record tool
    # from the project's effective stack, never by the model: {name, source ("project_selection"
    # | "bu_default" | "none"), warning, departures: ["what departs from the stack, and why"]}.
    # Optional so every brief recorded before it existed still reads.
    tech_stack: Optional[dict] = None
    recorded_at: Optional[str] = None
    agent_session_id: Optional[str] = None
    # 3: must_not_change and success-measure kinds (Phase D). Older briefs still load.
    version: int = 3


class DiscoveryArtifact(BaseModel):
    """-> runs.discovery_artifacts. Shape documented in
    agents_orchestrator/discovery_agent/analysis/assessment.py."""

    schema_version: int
    generated_at: str
    as_of: str
    target_stack: str = ""
    repository: Dict[str, Any]
    summary: Dict[str, Any]
    modules: List[Dict[str, Any]]
    dependency_graph: Dict[str, Any]
    flags: Dict[str, Any]
    scanners: Dict[str, Any]
    golden_master: Dict[str, Any]
    # Schema 2: what the code alone cannot tell (research §6.2). Without this field the
    # model would DROP it silently on persist (pydantic ignores unknown keys).
    not_assessable_statically: List[Dict[str, Any]] = []


class TargetDesignArtifact(BaseModel):
    """-> runs.target_design_artifacts (0071), and each frozen `design_modernization` version.

    The DESIGN is the hand-over packet's payload (`handover/packets.DesignPayload`, validated by
    `record_target_design` before this is built), stored field by field so the packet is read
    back with `emit.design_payload`. Around it, what the PAGE needs and the model never writes:
    which brief and assessment versions it was built from and the commit, each module's legacy
    path (the ledger's `legacy_path` on approval), the interface inventory's totals, the stack
    in force, and the non-blocking notes the checks produced.

    Every field is declared: pydantic drops unknown keys silently (Phase D trap)."""

    schema_version: int = 1
    system_name: str = ""
    # ── the design (DesignPayload) ──
    summary: str
    layers: List[Dict[str, Any]]
    modules: List[Dict[str, Any]]
    interop: Dict[str, Any] = {}
    ordering_constraints: List[str] = []
    frozen_contracts: List[Dict[str, Any]] = []
    data_migration: Optional[Dict[str, Any]] = None
    nfr: List[Dict[str, Any]] = []
    security_design: List[str] = []
    traps: List[Dict[str, Any]] = []
    adrs: List[Dict[str, Any]] = []
    diagrams: List[Dict[str, Any]] = []
    departures_from_brief: List[Dict[str, Any]] = []
    open_questions: List[str] = []
    resolved_questions: List[Dict[str, Any]] = []
    # ── set by the record tool, never by the model ──
    sources: Dict[str, Any] = {}
    module_paths: Dict[str, str] = {}
    interfaces: Optional[Dict[str, Any]] = None
    tech_stack: Optional[Dict[str, Any]] = None
    notes: List[str] = []
    recorded_at: Optional[str] = None
    agent_session_id: Optional[str] = None


class StrategyArtifact(BaseModel):
    """-> runs.strategy_artifacts (0072), and each frozen `strategy` version.

    The PLAN is the hand-over packet's payload (`handover/packets.PlanPayload`, validated by
    `record_migration_strategy` first), stored field by field (`freeze_policy.from` under its
    alias) so `emit.plan_payload` reads it back. Around it, what the page needs and the model
    never writes: the versions it was built from, the dependency-safe order and the calendar and
    effort checks as COMPUTED at record time, and each planned module's wave and criteria (the
    ledger placement approval applies). Every field declared: pydantic drops unknown keys."""

    schema_version: int = 1
    system_name: str = ""
    # ── the plan (PlanPayload) ──
    summary: str
    waves: List[Dict[str, Any]]
    order_exceptions: List[Dict[str, Any]] = []
    equivalence_criteria: List[Dict[str, Any]] = []
    baseline_plan: List[Dict[str, Any]] = []
    freeze_policy: Dict[str, Any]
    critical_path: List[str] = []
    calendar_conflicts: List[Dict[str, Any]] = []
    raid: Dict[str, Any] = {}
    effort: List[Dict[str, Any]] = []
    budget_fit: str = ""
    # ── set by the record tool, never by the model ──
    sources: Dict[str, Any] = {}
    placements: List[Dict[str, Any]] = []
    proposed_order: Optional[Dict[str, Any]] = None
    calendar_checked: List[Dict[str, Any]] = []
    effort_table: Optional[Dict[str, Any]] = None
    brief_dates: Dict[str, Any] = {}
    notes: List[str] = []
    recorded_at: Optional[str] = None
    agent_session_id: Optional[str] = None


class EquivalenceArtifact(BaseModel):
    """-> runs.equivalence_artifacts (0073), and each frozen `testing_modernization` version.

    Baseline mode (Phase G). The BASELINE is the hand-over packet's payload
    (`handover/packets.BaselinePayload`: BL-xx, noise reports, rule proposals, stubs, criteria not
    captured), which `emit.baseline_payload` reads back. Around it, what the page and the ledger need
    and the model never writes: the inputs it was built from, the capture (id, image, times — never a
    recording), the criterion → scenario mapping, each scenario's counts and masked noise, and the
    placements approval applies (module → BL ids). Every field declared: pydantic drops unknown keys."""

    schema_version: int = 1
    system_name: str = ""
    # ── the baseline (BaselinePayload) ──
    mode: str = "baseline"
    baselines: List[Dict[str, Any]]
    noise: List[Dict[str, Any]] = []
    rule_proposals: List[Dict[str, Any]] = []
    stubs: List[str] = []
    not_captured: List[Dict[str, Any]] = []
    # ── set by the record tool, never by the model ──
    sources: Dict[str, Any] = {}
    capture: Dict[str, Any] = {}
    mapping: Dict[str, List[str]] = {}
    scenarios: List[Dict[str, Any]] = []
    placements: List[Dict[str, Any]] = []
    notes: List[str] = []
    recorded_at: Optional[str] = None
    agent_session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Traceability and handoff helpers
# ---------------------------------------------------------------------------

_SENTINEL_PATTERN = re.compile(r"^(REQUIREMENTS_PAYLOAD|HANDOFF)::\s*", re.IGNORECASE)


class TraceLink(BaseModel):
    """Bidirectional traceability link between two artifact items."""

    from_id: str
    to_id: str
    kind: str


def validate_handoff(
    payload: Union[Dict[str, Any], str],
    model: type[BaseModel],
) -> BaseModel:
    """Parse and validate an agent handoff payload against a typed contract.

    Accepts:
      - A plain dict
      - A JSON string (with or without a leading ``REQUIREMENTS_PAYLOAD::`` /
        ``HANDOFF::`` sentinel and optional whitespace)

    Strips the sentinel prefix before parsing. On validation failure raises
    ``ValueError`` with the full Pydantic error detail so callers receive a
    precise diagnostic rather than a bare validation exception.
    """
    if isinstance(payload, str):
        payload = _SENTINEL_PATTERN.sub("", payload).strip()
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Handoff payload is not valid JSON: {exc}") from exc

    try:
        return model.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Handoff payload failed validation against {model.__name__}: {exc}") from exc
