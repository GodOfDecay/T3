"""The ten Track 3 hand-over packets: what each agent hands the next one.

WHY THESE EXIST BEFORE THE AGENTS. The Development Plan's §5 builds contract-first: every
packet is frozen as a schema with a ClaimTrack fixture instance, so an agent is built and
tested against the fixture of its inputs instead of waiting for the agent before it. The
fixtures live in `fixtures/claimtrack/`; `tests/modernization_common/test_handover_packets.py`
validates every one of them.

ONE MODEL, TWO USES. Each `*Payload` class is also what that agent's single record tool
validates (research §5.8 rule 5: "the tool validates it and refuses bad payloads, so the
rules are enforced in code as well as asked for in the prompt"). A validator message here IS
the refusal the model reads, so each says what is wrong and what to do about it.

WHAT IS CHECKED HERE, AND WHAT IS NOT. Only rules decidable from the packet alone: a module
with no pattern, an ADR with one option, a criterion with no comparison, a verdict that
contradicts its own findings. Rules that need another artifact or the file system — a
version past end of life (needs the assessment's EOL table), a file map missing a legacy
file (needs the checkout), a module in no wave (needs the design's module list) — belong to
the record tool that has that data, and are listed in each class's docstring so they are
not forgotten.

NOT MEASURED IS NOT ZERO (R39). Wherever a number might not have been produced — a scan that
did not run, a comparison not executed — the field is `Optional` and `None` means "not
measured". Validators refuse a `passed` / `PASS` that rests on a `None`.

STATUS VOCABULARY. The envelope's `status` is the artifact-version store's own
(`draft | published | superseded | rejected`, `shared/services/artifact_versions.py`), not
the research doc's `submitted | approved`: the envelope is read off the version row, and a
second vocabulary is a translation table waiting to drift. "Approved" in the documents means
`published` here.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ids import (
    AdrId, BaselineId, ContractId, CriterionId, CutoverStepId, DifferenceId, ModuleId,
    ReferenceId, ReviewFindingId, SecurityFindingId, TrapId, WaveId,
)


class _Strict(BaseModel):
    """Unknown keys are refused: a misspelt field is a lost field, silently."""

    model_config = ConfigDict(extra="forbid")


NonEmpty = Field(min_length=1)


def _dupes(values) -> list:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def _require_unique(values, what: str) -> None:
    dupes = _dupes(values)
    if dupes:
        raise ValueError(f"{what} must be unique; repeated: {', '.join(map(str, dupes))}")


# ── envelope (research §5.3) ─────────────────────────────────────────────────

ArtifactName = Literal[
    "migration_intent_payload", "discovery_artifacts", "target_design_artifacts",
    "strategy_artifacts", "equivalence_artifacts", "migration_artifacts",
    "migration_review_artifacts", "modernization_security_artifacts", "cutover_artifacts",
    "cutover_pack_artifacts",
]
VersionStatus = Literal["draft", "published", "superseded", "rejected"]


class BuiltFrom(_Strict):
    """One input this artifact was built from, pinned to the version that was read."""

    artifact: ArtifactName
    version: int = Field(ge=1)
    status: VersionStatus
    commit: Optional[str] = None


class ProducedBy(_Strict):
    user_id: Optional[str] = None
    model: Optional[str] = None
    run_id: Optional[str] = None


class _Envelope(_Strict):
    schema_version: Literal[1] = 1
    version: int = Field(ge=1)
    status: VersionStatus
    built_from: list[BuiltFrom] = []
    produced_by: ProducedBy = ProducedBy()
    produced_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _one_pin_per_input(self):
        _require_unique([b.artifact for b in self.built_from], "built_from artifacts")
        return self


# ── 1. Migration Intent brief → Dependency and Risk, Target Architecture ─────

MeasureKind = Literal["equivalence", "performance", "security", "schedule", "cost"]


class SuccessMeasure(_Strict):
    metric: str = NonEmpty
    today: Optional[str] = None
    target: str = NonEmpty
    kind: MeasureKind


class Scope(_Strict):
    in_scope: list[str] = Field(alias="in", min_length=1)
    out_of_scope: list[str] = Field(default=[], alias="out")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


MilestoneKind = Literal["start", "freeze", "compliance", "deadline", "cutover", "decommission", "other"]


class BriefMilestone(_Strict):
    """A dated commitment from the brief. Migration Strategy lays its waves against these."""

    date: date
    label: str = NonEmpty
    kind: MilestoneKind = "other"


class BriefPayload(_Strict):
    """The brief as later agents need it. `must_not_change` holds the user's own words
    (Target Architecture turns each into a CT-xx); a vague entry is a question the Migration
    Intent agent asks before recording, not something this model can judge."""

    system_name: str = NonEmpty
    goal: str = NonEmpty
    target_stack: list[str] = Field(min_length=1)
    scope: Scope
    constraints: list[str] = []
    deadline: Optional[date] = None
    budget: Optional[str] = None
    freeze_from: Optional[date] = None
    downtime_window: Optional[str] = None
    data_residency: Optional[str] = None
    must_not_change: list[str] = []
    success_measures: list[SuccessMeasure] = Field(min_length=1)
    business_owner: Optional[str] = None
    open_questions: list[str] = []
    milestones: list[BriefMilestone] = []

    @model_validator(mode="after")
    def _words_kept(self):
        if any(not item.strip() for item in self.must_not_change):
            raise ValueError("must_not_change has an empty entry; record the user's words or drop it")
        return self


class BriefPacket(_Envelope):
    agent_id: Literal["requirements_modernization"] = "requirements_modernization"
    artifact: Literal["migration_intent_payload"] = "migration_intent_payload"
    payload: BriefPayload


# ── 2. Dependency and Risk assessment → Target Architecture ──────────────────

Tier = Literal["mechanical", "llm_assisted", "manual"]
RuntimeStatus = Literal["eol", "approaching", "legacy", "supported", "unknown"]


class Runtime(_Strict):
    name: str = NonEmpty
    version: Optional[str] = None
    status: RuntimeStatus
    eol_date: Optional[date] = None


class AssessedModule(_Strict):
    id: ModuleId
    name: str = NonEmpty
    path: str = NonEmpty
    tier: Tier
    score: int = Field(ge=0, le=100)
    runtime: Optional[Runtime] = None
    loc: Optional[int] = Field(default=None, ge=0)
    fan_in: Optional[int] = Field(default=None, ge=0)
    flags: list[str] = []
    blockers: list[str] = []


class GoldenMaster(_Strict):
    status: Literal["not_captured", "captured"]
    baselines: list[BaselineId] = []

    @model_validator(mode="after")
    def _pointer_matches_status(self):
        if self.status == "captured" and not self.baselines:
            raise ValueError("golden_master is captured but names no baseline (BL-xx)")
        if self.status == "not_captured" and self.baselines:
            raise ValueError("golden_master names baselines but says not_captured")
        return self


class AssessmentFlags(_Strict):
    eol: list[str] = []
    deprecated: list[str] = []
    vulnerable: list[str] = []


class AssessmentPayload(_Strict):
    """Stable M-xx ids (stable within a commit) are minted by Dependency and Risk (Step 1)."""

    repository: str = NonEmpty
    commit: str = NonEmpty
    modules: list[AssessedModule] = Field(min_length=1)
    graph: list[tuple[ModuleId, ModuleId]] = []
    flags: AssessmentFlags = AssessmentFlags()
    golden_master: GoldenMaster = GoldenMaster(status="not_captured")
    not_assessable_statically: list[str] = []

    @model_validator(mode="after")
    def _consistent(self):
        ids = [m.id for m in self.modules]
        _require_unique(ids, "module ids")
        _require_unique([m.path for m in self.modules], "module paths")
        known = set(ids)
        for dependent, dependency in self.graph:
            missing = {dependent, dependency} - known
            if missing:
                raise ValueError(f"graph edge {dependent}→{dependency} names unknown module(s): "
                                 f"{', '.join(sorted(missing))}")
            if dependent == dependency:
                raise ValueError(f"graph edge {dependent}→{dependency} is a self-loop")
        return self


class AssessmentPacket(_Envelope):
    agent_id: Literal["discovery"] = "discovery"
    artifact: Literal["discovery_artifacts"] = "discovery_artifacts"
    payload: AssessmentPayload


# ── 3. Target design → Migration Strategy ────────────────────────────────────

Pattern = Literal["in_place_upgrade", "strangler_fig", "branch_by_abstraction", "parallel_run",
                  "rewrite", "replatform", "retire", "keep"]
#: What a frozen contract IS, for any system: an HTTP API, an RPC interface (SOAP, gRPC, RMI,
#: CORBA), a file exchanged, a report, a database others read or write, a queue or event, a UI
#: screen other people work in, a scheduled job others depend on, or a library other systems
#: link against.
ContractKind = Literal["http", "rpc", "file", "report", "db", "queue", "event", "ui", "job", "library"]


class Layer(_Strict):
    layer: str = NonEmpty
    today: str = NonEmpty
    target: str = NonEmpty
    modules: list[ModuleId] = []


class DesignedModule(_Strict):
    module_id: ModuleId
    module: str = NonEmpty
    tier: Tier
    risk_score: int = Field(ge=0, le=100)
    patterns: list[Pattern] = Field(
        min_length=1, max_length=2,
        description="From the fixed vocabulary; a module may combine two.")
    rationale: str = NonEmpty
    adr_ids: list[AdrId] = []
    contract_ids: list[ContractId] = []


class Interop(_Strict):
    routing: str = ""
    data: str = ""
    shared_libraries: str = ""
    jobs: str = ""
    identity: str = ""


class FrozenContract(_Strict):
    id: ContractId
    name: str = NonEmpty
    kind: ContractKind
    legacy_location: str = Field(min_length=1, description="path[:line] in the legacy code")
    consumers: list[str] = []
    proof: str = NonEmpty
    status: Literal["confirmed", "proposed"]
    brief_item: Optional[str] = Field(
        default=None,
        description="The brief's must-not-change entry this contract freezes, word for word; "
                    "None for a contract the brief did not name.")


class ResolvedQuestion(_Strict):
    """A question the assessment could not answer from the code (`not_assessable_statically`),
    and the answer the design rests on — from the user or an approved document, never a guess."""

    question: str = NonEmpty
    answer: str = NonEmpty
    source: Literal["user", "document"]


class DataMigration(_Strict):
    source: str = NonEmpty
    target: str = NonEmpty
    method: str = NonEmpty
    behaviour_changes: list[str] = []
    cutover: str = NonEmpty


class Nfr(_Strict):
    measure: str = NonEmpty
    target: str = NonEmpty
    source: Literal["brief", "design"]


class Trap(_Strict):
    id: TrapId
    change: str = NonEmpty
    affects: list[ModuleId] = Field(min_length=1)
    where: str = NonEmpty
    effect: str = NonEmpty
    contract_ids: list[ContractId] = []


class Adr(_Strict):
    id: AdrId
    title: str = NonEmpty
    context: str = NonEmpty
    options: list[str] = Field(min_length=2, description="At least two options considered.")
    decision: str = NonEmpty
    consequences: str = NonEmpty
    modules: list[ModuleId] = []
    contracts: list[ContractId] = []


class Diagram(_Strict):
    title: str = NonEmpty
    mermaid: str = NonEmpty


class Departure(_Strict):
    brief_said: str = NonEmpty
    design_says: str = NonEmpty
    adr_id: AdrId


class DesignPayload(_Strict):
    """Refusals checked here: a module with no pattern, a pattern outside the vocabulary, a
    contract with no legacy location, an ADR with fewer than two options, and any reference
    to a contract/ADR/module the design does not define.

    Checked by `record_target_design` (needs other data — `design_modernization_agent/analysis/
    checks.py`): a version past end of life (the EOL table); every assessed module present, with
    the id, name, tier and score of the PINNED assessment (D14); every must-not-change item frozen
    by a contract (`brief_item`); a contract not found by `capture_legacy_interfaces` and not
    named by the brief may only be `proposed`; locations that exist in the checkout; the data
    migration when the database changes; the three diagrams; every not-assessable question
    answered or kept open.
    """

    summary: str = NonEmpty
    layers: list[Layer] = Field(min_length=1)
    modules: list[DesignedModule] = Field(min_length=1)
    interop: Interop = Interop()
    ordering_constraints: list[str] = []
    frozen_contracts: list[FrozenContract] = []
    data_migration: Optional[DataMigration] = None
    nfr: list[Nfr] = []
    security_design: list[str] = []
    traps: list[Trap] = []
    adrs: list[Adr] = []
    diagrams: list[Diagram] = []
    departures_from_brief: list[Departure] = []
    open_questions: list[str] = []
    resolved_questions: list[ResolvedQuestion] = []

    @model_validator(mode="after")
    def _references_resolve(self):
        modules = [m.module_id for m in self.modules]
        contracts = [c.id for c in self.frozen_contracts]
        adrs = [a.id for a in self.adrs]
        _require_unique(modules, "module ids")
        _require_unique(contracts, "contract ids")
        _require_unique([t.id for t in self.traps], "trap ids")
        _require_unique(adrs, "ADR ids")
        for label, used, known in (
            ("module contract_ids", {c for m in self.modules for c in m.contract_ids}, contracts),
            ("module adr_ids", {a for m in self.modules for a in m.adr_ids}, adrs),
            ("trap contract_ids", {c for t in self.traps for c in t.contract_ids}, contracts),
            ("trap affects", {m for t in self.traps for m in t.affects}, modules),
            ("ADR modules", {m for a in self.adrs for m in a.modules}, modules),
            ("ADR contracts", {c for a in self.adrs for c in a.contracts}, contracts),
            ("layer modules", {m for layer in self.layers for m in layer.modules}, modules),
            ("departure adr_id", {d.adr_id for d in self.departures_from_brief}, adrs),
        ):
            unknown = sorted(used - set(known))
            if unknown:
                raise ValueError(f"{label} cite ids this design does not define: {', '.join(unknown)}")
        return self


class DesignPacket(_Envelope):
    agent_id: Literal["design_modernization"] = "design_modernization"
    artifact: Literal["target_design_artifacts"] = "target_design_artifacts"
    payload: DesignPayload


# ── 4. Migration plan → Equivalence Testing (baseline), Migration Development ─

Comparison = Literal["exact", "byte_identical", "numeric_tolerance", "schema_equal", "set_equal",
                     "percentile_threshold"]
_NEEDS_THRESHOLD = {"numeric_tolerance", "percentile_threshold"}


class ParallelRun(_Strict):
    required: bool
    period: Optional[str] = None
    system_of_record: Literal["legacy", "new"] = "legacy"


class Rollback(_Strict):
    trigger: str = Field(min_length=1, description="What makes the wave roll back.")
    method: str = Field(min_length=1, description="How it rolls back.")
    max_time: Optional[str] = None


class Wave(_Strict):
    id: WaveId
    name: str = NonEmpty
    modules: list[ModuleId] = []
    patterns: dict[ModuleId, list[Pattern]] = {}
    starts: date
    ends: date
    date_status: Literal["given", "proposed"]
    entry_criteria: list[str] = []
    exit_criteria: list[str] = Field(min_length=1)
    parallel_run: ParallelRun = ParallelRun(required=False)
    cutover_window: Optional[str] = None
    rollback: Rollback
    owner: Optional[str] = None
    order_reason: str = NonEmpty

    @model_validator(mode="after")
    def _dates_and_modules(self):
        if self.ends < self.starts:
            raise ValueError(f"{self.id} ends ({self.ends}) before it starts ({self.starts})")
        if self.id != "W0" and not self.modules:
            raise ValueError(f"{self.id} moves no module; only W0 (the foundation) may be empty")
        if self.id == "W0" and self.modules:
            raise ValueError(f"W0 is the foundation and moves no module; put {', '.join(self.modules)} in W1 or later")
        if self.modules and not [c for c in self.entry_criteria if c.strip()]:
            raise ValueError(f"{self.id} has no entry criteria; say what must be true before it starts")
        stray = sorted(set(self.patterns) - set(self.modules))
        if stray:
            raise ValueError(f"{self.id} gives patterns for modules it does not move: {', '.join(stray)}")
        return self


class NormalizationRule(_Strict):
    field: str = NonEmpty
    rule: str = NonEmpty
    reason: str = Field(min_length=1, description="Why this field may differ. Required.")


class Criterion(_Strict):
    id: CriterionId
    module_id: ModuleId | Literal["all"]
    protects: list[ContractId | TrapId] = []
    protects_measures: list[str] = Field(
        default=[], description="Brief success measures protected, in the brief's words (they have no id).")
    observable: str = Field(min_length=1)
    input_set: str = Field(min_length=1)
    comparison: Comparison
    normalization: list[NormalizationRule] = []
    threshold: Optional[str] = None

    @model_validator(mode="after")
    def _threshold_when_needed(self):
        if not (self.protects or self.protects_measures):
            raise ValueError(f"{self.id} protects nothing; name the contract, trap or success measure")
        if self.comparison in _NEEDS_THRESHOLD and not self.threshold:
            raise ValueError(f"{self.id} compares by {self.comparison} but gives no threshold")
        _require_unique([r.field for r in self.normalization], f"{self.id} normalization fields")
        return self


class BaselinePlanItem(_Strict):
    ec_id: CriterionId
    inputs: str = NonEmpty
    environment: str = NonEmpty
    data_source: str = NonEmpty
    masking: str = NonEmpty
    due: date


class FreezePolicy(_Strict):
    from_: date = Field(alias="from")
    allowed: str = NonEmpty
    carry_forward: str = NonEmpty

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CalendarConflict(_Strict):
    conflict: str = NonEmpty
    impact: str = NonEmpty
    options: list[str] = []
    resolution: Optional[str] = None
    ref: Optional[str] = Field(
        default=None, description="The `check_calendar` reference this reports (e.g. deadline:W4); "
                                  "None for a conflict the user raised that no check computes.")


class OrderException(_Strict):
    """A module that moves in an EARLIER wave than something it depends on. Only allowed when the
    target design says how both sides coexist meanwhile — an ADR (dual build, a facade, an
    abstraction), cited by id."""

    module_id: ModuleId
    depends_on: ModuleId
    reason: str = NonEmpty
    adr_id: AdrId


class Risk(_Strict):
    risk: str = NonEmpty
    evidence: str = NonEmpty
    mitigation: str = NonEmpty


class Raid(_Strict):
    risks: list[Risk] = []
    assumptions: list[str] = []
    issues: list[str] = []
    dependencies: list[str] = []


class Effort(_Strict):
    wave: WaveId
    band: str = NonEmpty
    basis: str = NonEmpty
    is_estimate: Literal[True] = True


class PlanPayload(_Strict):
    """Refusals checked here: a module in two waves; no W0; a criterion without an observable,
    an input set or a comparison; a normalization rule without a reason; a wave without a
    rollback; a baseline-plan item for a criterion the plan does not define.

    Checked by `record_migration_strategy` (`strategy_agent/analysis/checks.py`): every module
    the design moves is in a wave, with the design's patterns; the order respects the dependency
    graph unless an `order_exceptions` entry cites a design ADR; every contract, trap and
    equivalence/performance/security success measure is protected; every calendar conflict the
    check computes is reported; the brief's freeze date is kept."""

    summary: str = NonEmpty
    waves: list[Wave] = Field(min_length=1)
    order_exceptions: list[OrderException] = []
    equivalence_criteria: list[Criterion] = []
    baseline_plan: list[BaselinePlanItem] = []
    freeze_policy: FreezePolicy
    critical_path: list[str] = []
    calendar_conflicts: list[CalendarConflict] = []
    raid: Raid = Raid()
    effort: list[Effort] = []
    budget_fit: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        wave_ids = [w.id for w in self.waves]
        _require_unique(wave_ids, "wave ids")
        if "W0" not in wave_ids:
            raise ValueError("there is no W0; wave 0 is always the foundation (environments, "
                             "pipelines, data platform, observability, baseline capture)")
        placed = [m for w in self.waves for m in w.modules]
        twice = _dupes(placed)
        if twice:
            raise ValueError(f"modules placed in more than one wave: {', '.join(twice)}")
        ec_ids = [c.id for c in self.equivalence_criteria]
        _require_unique(ec_ids, "criterion ids")
        unplanned_modules = sorted({c.module_id for c in self.equivalence_criteria}
                                   - set(placed) - {"all"})
        if unplanned_modules:
            raise ValueError(f"criteria name modules that are in no wave: {', '.join(unplanned_modules)}")
        stray = sorted({b.ec_id for b in self.baseline_plan} - set(ec_ids))
        if stray:
            raise ValueError(f"baseline plan names criteria the plan does not define: {', '.join(stray)}")
        effort_waves = sorted({e.wave for e in self.effort} - set(wave_ids))
        if effort_waves:
            raise ValueError(f"effort names waves the plan does not define: {', '.join(effort_waves)}")
        cited = sorted({ec for w in self.waves for text in w.exit_criteria + w.entry_criteria
                        for ec in re.findall(r"\bEC-\d{2,}\b", text)} - set(ec_ids))
        if cited:
            raise ValueError(f"wave criteria cite criteria the plan does not define: {', '.join(cited)}")
        unplaced = sorted({m for x in self.order_exceptions for m in (x.module_id, x.depends_on)} - set(placed))
        if unplaced:
            raise ValueError(f"order exceptions name modules that are in no wave: {', '.join(unplaced)}")
        _require_unique([c.ref for c in self.calendar_conflicts if c.ref], "calendar conflict refs")
        return self


class PlanPacket(_Envelope):
    agent_id: Literal["strategy"] = "strategy"
    artifact: Literal["strategy_artifacts"] = "strategy_artifacts"
    payload: PlanPayload


# ── 5. Baseline → Migration Development, Equivalence Testing (verify) ────────

_SHA256 = r"^[0-9a-f]{64}$"


class Baseline(_Strict):
    id: BaselineId
    ec_ids: list[CriterionId] = Field(min_length=1)
    module_id: ModuleId | Literal["all"]
    count: int = Field(ge=1, description="How many recorded cases/runs/reports/journeys.")
    unit: Literal["cases", "runs", "reports", "journeys", "samples"]
    sha256: str = Field(pattern=_SHA256)
    region: str = NonEmpty
    noise_fields: list[str] = []
    measurements: dict[str, float] = {}
    captured_at: Optional[datetime] = None


class RuleProposal(_Strict):
    """A normalization rule PROPOSED to Migration Strategy. Testing never applies one."""

    ec_id: CriterionId
    field: str = NonEmpty
    rule: str = NonEmpty
    evidence: str = NonEmpty


class NoiseReport(_Strict):
    ec_id: CriterionId
    runs_compared: int = Field(ge=2, description="Legacy is run twice at least.")
    varying_fields: list[str] = []
    covered_by_rule: list[str] = []


class NotCaptured(_Strict):
    """A criterion of a baselined module that Baseline mode could not record (a load test, a UI
    journey) — said, with why, instead of silently missing (Phase G)."""

    ec_id: CriterionId
    reason: str = Field(min_length=3)


class BaselinePayload(_Strict):
    mode: Literal["baseline"] = "baseline"
    baselines: list[Baseline] = Field(min_length=1)
    noise: list[NoiseReport] = []
    rule_proposals: list[RuleProposal] = []
    stubs: list[str] = []
    not_captured: list[NotCaptured] = []

    @model_validator(mode="after")
    def _every_uncovered_noise_is_proposed(self):
        _require_unique([b.id for b in self.baselines], "baseline ids")
        _require_unique([n.ec_id for n in self.not_captured], "criteria not captured")
        both = sorted({e for b in self.baselines for e in b.ec_ids} & {n.ec_id for n in self.not_captured})
        if both:
            raise ValueError(f"{', '.join(both)} are both baselined and listed as not captured")
        proposed = {(p.ec_id, p.field) for p in self.rule_proposals}
        for report in self.noise:
            for fld in report.varying_fields:
                if fld not in report.covered_by_rule and (report.ec_id, fld) not in proposed:
                    raise ValueError(
                        f"{fld} varies between legacy runs for {report.ec_id} and no rule covers it; "
                        "propose a normalization rule to Migration Strategy (do not apply one)")
        return self


class BaselinePacket(_Envelope):
    agent_id: Literal["testing_modernization"] = "testing_modernization"
    artifact: Literal["equivalence_artifacts"] = "equivalence_artifacts"
    payload: BaselinePayload


# ── 6. Module migration record → Migration Review, Security ──────────────────

MAX_BUILD_ROUNDS = 5


class Recipe(_Strict):
    tool: str = NonEmpty
    version: str = Field(min_length=1, description="Pinned; never 'latest'.")
    args: str = ""

    @model_validator(mode="after")
    def _pinned(self):
        if self.version.strip().lower() in {"latest", "*", "any"}:
            raise ValueError(f"recipe {self.tool} is not pinned ({self.version!r}); give the exact version")
        return self


class FileMapEntry(_Strict):
    legacy_path: str = NonEmpty
    disposition: Literal["mapped", "merged", "dropped"]
    target_path: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _explained(self):
        if self.disposition in ("mapped", "merged") and not self.target_path:
            raise ValueError(f"{self.legacy_path} is {self.disposition} but names no target file")
        if self.disposition == "dropped" and not (self.reason or "").strip():
            raise ValueError(f"{self.legacy_path} is dropped without a reason")
        return self


class BuildResult(_Strict):
    status: Literal["green", "red", "not_run"]
    rounds: int = Field(ge=0, le=MAX_BUILD_ROUNDS)
    failing: Optional[str] = None


class Rewritten(_Strict):
    file: str = NonEmpty
    reason: str = NonEmpty


class MigrationRecordPayload(_Strict):
    """`outcome` resolves a disagreement between the documents: the Flow document says the
    record tool refuses a red build, and research §6.6 says a build still red after five
    rounds is "recorded". Both hold with an outcome: `ready_for_review` requires green;
    `build_failed` records the red build and why; `blocked` is the manual tier's hand-off,
    with no code written.

    Refusals checked here: a file-map entry without a target or (when dropped) a reason; a
    legacy path outside the module's legacy path; more than five build rounds; an unpinned
    recipe; `ready_for_review` without a green build or without a file map.

    Checked by `record_module_migration`: the map covers EVERY legacy file in the module (needs
    the checkout); nothing was written outside the module's target path (needs the diff)."""

    module_id: ModuleId
    outcome: Literal["ready_for_review", "build_failed", "blocked"]
    legacy_module_path: str = NonEmpty
    target_branch: Optional[str] = None
    pr_url: Optional[str] = None
    recipes: list[Recipe] = []
    file_map: list[FileMapEntry] = []
    llm_rewritten: list[Rewritten] = []
    traps_handled: dict[TrapId, str] = {}
    vault_references: list[str] = []
    build: BuildResult
    manual_follow_ups: list[str] = []
    handoff_note: Optional[str] = None

    @model_validator(mode="after")
    def _consistent(self):
        _require_unique([e.legacy_path for e in self.file_map], "file-map legacy paths")
        prefix = self.legacy_module_path.rstrip("/") + "/"
        outside = sorted(e.legacy_path for e in self.file_map if not e.legacy_path.startswith(prefix))
        if outside:
            raise ValueError(f"file map lists legacy files outside {self.legacy_module_path}: {', '.join(outside)}")
        if self.outcome == "ready_for_review":
            if self.build.status != "green":
                raise ValueError(f"the build is {self.build.status}; only a green build is ready for review")
            if not self.file_map:
                raise ValueError("ready_for_review needs the legacy→target file map")
        if self.outcome == "build_failed" and (self.build.status != "red" or not self.build.failing):
            raise ValueError("build_failed needs a red build and what is failing")
        if self.outcome == "blocked":
            if not (self.handoff_note or "").strip():
                raise ValueError("a blocked module needs the hand-off note: what a person must redesign and why")
            if self.file_map or self.recipes or self.llm_rewritten:
                raise ValueError("a blocked (manual-tier) module has no code written; drop the file map and recipes")
        return self


class MigrationRecordPacket(_Envelope):
    agent_id: Literal["development_modernization"] = "development_modernization"
    artifact: Literal["migration_artifacts"] = "migration_artifacts"
    payload: MigrationRecordPayload


# ── 7. Migration review → Migration Development (rework), Cutover ───────────

Severity = Literal["critical", "high", "medium", "low", "info"]
_BLOCKING = {"critical", "high"}
_BLOCKING_CATEGORIES = {"contract_drift", "trap_unhandled", "behaviour_change", "introduced"}


class ReviewFinding(_Strict):
    id: ReviewFindingId
    severity: Severity
    category: Literal["contract_drift", "trap_unhandled", "behaviour_change", "carried_over",
                      "introduced", "scope_creep", "traceability", "design", "maintainability", "style"]
    file: str = NonEmpty
    line: Optional[int] = Field(default=None, ge=1)
    legacy_file: Optional[str] = None
    legacy_line: Optional[int] = Field(default=None, ge=1)
    description: str = NonEmpty
    recommendation: str = NonEmpty
    refs: list[ReferenceId] = []
    autofix_patch: Optional[str] = None


class CoverageCheck(_Strict):
    ec_id: CriterionId
    status: Literal["covered", "at_risk", "not_addressed"]
    note: str = ""


class ContractCheck(_Strict):
    ct_id: ContractId
    status: Literal["unchanged", "changed_allowed", "changed"]
    note: str = ""


class TrapCheck(_Strict):
    tr_id: TrapId
    status: Literal["handled", "not_handled", "not_applicable"]
    where: str = ""


class Traceability(_Strict):
    legacy_path: str = NonEmpty
    target_path: Optional[str] = None
    status: Literal["mapped", "merged", "dropped_justified", "missing"]


class KnownDebt(_Strict):
    pattern: str = NonEmpty
    legacy_file: str = NonEmpty
    note: str = ""


class FilesRead(_Strict):
    target: list[str] = []
    legacy: list[str] = []


class ReviewPayload(_Strict):
    """The merge-recommendation rules (research §6.7) are enforced here, so a model cannot
    `approve` a review whose own findings say otherwise.

    Checked by `submit_migration_review`: every file cited is in `files_read`, and every file
    in `files_read` was actually opened this run (needs the tool log)."""

    module_id: ModuleId
    pr: str = NonEmpty
    summary: str = NonEmpty
    merge_recommendation: Literal["approve", "request_changes", "needs_discussion"]
    findings: list[ReviewFinding] = []
    equivalence_coverage: list[CoverageCheck] = []
    contract_check: list[ContractCheck] = []
    trap_check: list[TrapCheck] = []
    traceability: list[Traceability] = []
    known_debt: list[KnownDebt] = []
    files_read: FilesRead

    def must_request_changes(self) -> list[str]:
        """The findings that force `request_changes`, by id."""
        return [f.id for f in self.findings
                if f.severity in _BLOCKING and f.category in _BLOCKING_CATEGORIES]

    @model_validator(mode="after")
    def _recommendation_follows_findings(self):
        _require_unique([f.id for f in self.findings], "finding ids")
        forcing = self.must_request_changes()
        if forcing and self.merge_recommendation != "request_changes":
            raise ValueError(f"{', '.join(forcing)} force request_changes "
                             f"(high/critical contract drift, unhandled trap, behaviour change or introduced issue)")
        if self.merge_recommendation == "approve":
            blocking = [f.id for f in self.findings if f.severity in _BLOCKING]
            changed = [c.ct_id for c in self.contract_check if c.status == "changed"]
            unhandled = [t.tr_id for t in self.trap_check if t.status == "not_handled"]
            missing = [t.legacy_path for t in self.traceability if t.status == "missing"]
            reasons = [f"{label}: {', '.join(ids)}" for label, ids in (
                ("critical/high findings", blocking), ("contracts changed without an ADR", changed),
                ("traps not handled", unhandled), ("legacy files unaccounted for", missing)) if ids]
            if reasons:
                raise ValueError("cannot approve — " + "; ".join(reasons))
        return self


class ReviewPacket(_Envelope):
    agent_id: Literal["code_review_modernization"] = "code_review_modernization"
    artifact: Literal["migration_review_artifacts"] = "migration_review_artifacts"
    payload: ReviewPayload


# ── 8. Security report → Migration Development (rework), Cutover ────────────

ScanStatus = Literal["ran", "cached", "not_installed", "failed", "not_run"]
_REQUIRED_SCANS = ("trivy", "semgrep", "gitleaks")


class SecurityFinding(_Strict):
    id: SecurityFindingId
    title: str = NonEmpty
    severity: Severity
    origin: Literal["carried_over", "introduced"]
    legacy_ref: Optional[str] = None
    reachable: Optional[bool] = Field(default=None, description="None = reachability not analysed.")
    is_secret: bool = False
    cve: Optional[str] = None
    package: Optional[str] = None
    file: Optional[str] = None
    remediation_plan: Optional[str] = None
    remediation_due: Optional[date] = None

    @model_validator(mode="after")
    def _carried_over_cites_legacy(self):
        if self.origin == "carried_over" and not self.legacy_ref:
            raise ValueError(f"{self.id} is carried over but gives no legacy_ref (path or package@version)")
        return self


class FixedFromLegacy(_Strict):
    title: str = NonEmpty
    cve: Optional[str] = None
    package: Optional[str] = None
    legacy_ref: str = NonEmpty


class ContractAuthz(_Strict):
    ct_id: ContractId
    status: Literal["same", "stricter", "weaker"]
    note: str = ""


class Sbom(_Strict):
    components: Optional[int] = Field(default=None, ge=0, description="None = not generated.")
    vulnerabilities: Optional[int] = Field(default=None, ge=0, description="None = not scanned, NEVER 0.")


class SecurityPayload(_Strict):
    """The Track 3 sign-off policy (research §6.8) is computed here by `required_verdict`, and a
    stated verdict that disagrees with it is refused. Two conservative readings, recorded in
    the build log: unknown reachability on a critical/high counts as reachable; and a required
    scanner that did not run means the verdict cannot be PASS (not scanned is not clean)."""

    module_id: ModuleId
    pr: str = NonEmpty
    legacy_commit: str = NonEmpty
    scans: dict[str, ScanStatus]
    findings: list[SecurityFinding] = []
    fixed_from_legacy: list[FixedFromLegacy] = []
    contract_authz: list[ContractAuthz] = []
    sbom: Sbom = Sbom()
    verdict: Literal["FAIL", "CONDITIONAL", "PASS"]
    rationale: str = NonEmpty

    def required_verdict(self) -> Literal["FAIL", "CONDITIONAL", "PASS", "INCOMPLETE"]:
        if any(f.is_secret and f.origin == "carried_over" for f in self.findings):
            return "FAIL"
        if any(f.severity in _BLOCKING and f.reachable is not False for f in self.findings):
            return "FAIL"
        if any(c.status == "weaker" for c in self.contract_authz):
            return "FAIL"  # a weaker contract authz is a high finding by policy
        if self.findings:
            return "CONDITIONAL"
        if any(self.scans.get(tool) not in ("ran", "cached") for tool in _REQUIRED_SCANS):
            return "INCOMPLETE"
        return "PASS"

    @model_validator(mode="after")
    def _verdict_follows_policy(self):
        _require_unique([f.id for f in self.findings], "finding ids")
        for f in self.findings:
            if f.severity not in _BLOCKING or f.reachable is False:
                if self.verdict == "CONDITIONAL" and not (f.remediation_plan and f.remediation_due):
                    raise ValueError(f"CONDITIONAL needs a remediation plan and a date for {f.id}")
        required = self.required_verdict()
        if required == "INCOMPLETE":
            missing = [t for t in _REQUIRED_SCANS if self.scans.get(t) not in ("ran", "cached")]
            if self.verdict == "PASS":
                raise ValueError(f"cannot PASS: {', '.join(missing)} did not run — not scanned is not clean")
        elif self.verdict != required:
            raise ValueError(f"the policy gives {required}, not {self.verdict}")
        return self


class SecurityPacket(_Envelope):
    agent_id: Literal["security_modernization"] = "security_modernization"
    artifact: Literal["modernization_security_artifacts"] = "modernization_security_artifacts"
    payload: SecurityPayload


# ── 9. Equivalence results (verify) → Cutover ────────────────────────────────

class ReplayedBaseline(_Strict):
    id: BaselineId
    version: int = Field(ge=1)


class CriterionResult(_Strict):
    ec_id: CriterionId
    verdict: Literal["passed", "failed", "open", "not_run"]
    cases_compared: Optional[int] = Field(default=None, ge=0, description="None = not run.")
    normalization_applied: list[str] = []


class Difference(_Strict):
    id: DifferenceId
    ec_id: CriterionId
    classification: Literal["regression", "normalization_gap", "accepted_change", "environment"]
    field: str = NonEmpty
    cases: int = Field(ge=1)
    masked_example: str = NonEmpty
    likely_area: Optional[str] = None
    adr_id: Optional[AdrId] = None

    @model_validator(mode="after")
    def _accepted_cites_adr(self):
        if self.classification == "accepted_change" and not self.adr_id:
            raise ValueError(f"{self.id} is an accepted change but cites no ADR allowing it")
        return self


class Performance(_Strict):
    ec_id: CriterionId
    legacy_p95_ms: Optional[float] = Field(default=None, ge=0)
    target_p95_ms: Optional[float] = Field(default=None, ge=0)
    threshold_ms: float = Field(gt=0)


class EquivalencePayload(_Strict):
    """Refusals checked here: `passed` on a criterion that was not run or that has a regression
    or an open normalization gap; `not_run` with cases compared; a performance criterion passed
    without both numbers or over its threshold.

    Normalization rules cannot be changed here: there is no field for them, only proposals."""

    mode: Literal["verify"] = "verify"
    module_id: ModuleId
    pr: str = NonEmpty
    baselines_replayed: list[ReplayedBaseline] = Field(min_length=1)
    criteria: list[CriterionResult] = Field(min_length=1)
    differences: list[Difference] = []
    performance: list[Performance] = []
    rule_proposals: list[RuleProposal] = []
    runs: int = Field(ge=1)

    def module_verdict(self) -> Literal["verified", "migrating", "open"]:
        verdicts = {c.verdict for c in self.criteria}
        if "failed" in verdicts:
            return "migrating"
        if verdicts == {"passed"}:
            return "verified"
        return "open"

    @model_validator(mode="after")
    def _verdicts_follow_evidence(self):
        _require_unique([c.ec_id for c in self.criteria], "criteria")
        _require_unique([d.id for d in self.differences], "difference ids")
        by_ec: dict[str, set[str]] = {}
        for d in self.differences:
            by_ec.setdefault(d.ec_id, set()).add(d.classification)
        perf = {p.ec_id: p for p in self.performance}
        for c in self.criteria:
            kinds = by_ec.get(c.ec_id, set())
            if c.verdict == "not_run" and c.cases_compared:
                raise ValueError(f"{c.ec_id} is not_run but reports {c.cases_compared} cases compared")
            if c.verdict == "passed":
                if not c.cases_compared:
                    raise ValueError(f"{c.ec_id} cannot pass: nothing was compared (a run that did not happen is not_run)")
                if "regression" in kinds:
                    raise ValueError(f"{c.ec_id} has a regression and cannot pass")
                if "normalization_gap" in kinds:
                    raise ValueError(f"{c.ec_id} has a normalization gap; it stays open until the plan is revised")
                p = perf.get(c.ec_id)
                if p is not None:
                    if p.legacy_p95_ms is None or p.target_p95_ms is None:
                        raise ValueError(f"{c.ec_id} is a performance criterion; both sides must be measured to pass")
                    if p.target_p95_ms > p.threshold_ms:
                        raise ValueError(f"{c.ec_id} target p95 {p.target_p95_ms} ms exceeds {p.threshold_ms} ms")
        unknown = sorted(set(by_ec) - {c.ec_id for c in self.criteria})
        if unknown:
            raise ValueError(f"differences name criteria with no result: {', '.join(unknown)}")
        return self


class EquivalencePacket(_Envelope):
    agent_id: Literal["testing_modernization"] = "testing_modernization"
    artifact: Literal["equivalence_artifacts"] = "equivalence_artifacts"
    payload: EquivalencePayload


# ── 10. Cutover plan → Cutover Pack ──────────────────────────────────────────

Gate = Literal["green", "red"]
_GATES = ("baseline", "review", "security", "equivalence", "pr_merged")


class Waiver(_Strict):
    gate: Literal["baseline", "review", "security", "equivalence", "pr_merged"]
    approver: str = NonEmpty
    reason: str = NonEmpty


class Readiness(_Strict):
    module_id: ModuleId
    baseline: Gate
    review: Gate
    security: Gate
    equivalence: Gate
    pr_merged: Gate
    closes_red: dict[str, str] = Field(default={}, description="gate → who closes it")
    waivers: list[Waiver] = []

    def open_reds(self) -> list[str]:
        waived = {w.gate for w in self.waivers}
        return [g for g in _GATES if getattr(self, g) == "red" and g not in waived]


class CutoverStep(_Strict):
    id: CutoverStepId
    action: str = NonEmpty
    owner: str = NonEmpty
    at: str = NonEmpty
    minutes: Optional[int] = Field(default=None, ge=0)
    counts_as_downtime: bool = False
    rollback_trigger: str = NonEmpty
    rollback_action: str = NonEmpty
    status: Literal["planned", "requested", "approved", "done", "rolled_back"] = "planned"


class TrafficStep(_Strict):
    step_id: CutoverStepId
    percent: int = Field(ge=0, le=100)
    hold: str = NonEmpty
    guards: list[str] = Field(min_length=1)


class SenderDay(_Strict):
    day: date
    sender: Literal["legacy", "new"]


class ParallelRunPlan(_Strict):
    """One entry per outbound file or call, one sender per day by construction."""

    outbound: str = NonEmpty
    days: list[SenderDay] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_sender_per_day(self):
        twice = _dupes([d.day for d in self.days])
        if twice:
            raise ValueError(f"{self.outbound}: a day appears twice (two senders?): "
                             f"{', '.join(map(str, twice))}")
        return self


class DecommissionItem(_Strict):
    id: CutoverStepId
    item: str = NonEmpty
    order: int = Field(ge=1)


class SignOffSlot(_Strict):
    role: Literal["devops_engineer", "business_owner"]
    user_id: Optional[str] = None
    approved_as: Optional[Literal["owner", "fallback:project_admin"]] = None


class CutoverPayload(_Strict):
    """Refusals checked here: `go` with an unwaived red gate (the model cannot turn a red green);
    downtime over the window not reported; a traffic shift that does not end at 100 or goes
    backwards; two senders on one day; decommission before hypercare closed green or out of
    order; one person in both sign-off slots.

    Checked by the tools: readiness itself is computed by `readiness_check`, never supplied;
    no step runs without an approved request (`request_cutover_step`)."""

    wave_id: WaveId
    window: str = NonEmpty
    downtime_limit_minutes: int = Field(ge=0)
    readiness: list[Readiness] = Field(min_length=1)
    go: bool
    steps: list[CutoverStep] = []
    downtime_exceeds_window: bool = False
    traffic_shift: list[TrafficStep] = []
    parallel_runs: list[ParallelRunPlan] = []
    hypercare: Literal["not_started", "open", "closed_green", "closed_red"] = "not_started"
    decommission: list[DecommissionItem] = []
    sign_off: list[SignOffSlot] = []

    def planned_downtime(self) -> int:
        return sum(s.minutes or 0 for s in self.steps if s.counts_as_downtime)

    @model_validator(mode="after")
    def _safe(self):
        _require_unique([s.id for s in self.steps], "step ids")
        reds = {r.module_id: r.open_reds() for r in self.readiness if r.open_reds()}
        if self.go and reds:
            detail = "; ".join(f"{m}: {', '.join(g)}" for m, g in reds.items())
            raise ValueError(f"NO-GO: red gates without an approved waiver — {detail}")
        over = self.planned_downtime() > self.downtime_limit_minutes
        if over != self.downtime_exceeds_window:
            raise ValueError(
                f"planned downtime is {self.planned_downtime()} min against a {self.downtime_limit_minutes}-min "
                f"window; downtime_exceeds_window must be {str(over).lower()} (report it, never plan around it)")
        percents = [t.percent for t in self.traffic_shift]
        if percents:
            if percents != sorted(percents) or percents[-1] != 100:
                raise ValueError(f"traffic shift {percents} must only increase and end at 100")
        _require_unique([p.outbound for p in self.parallel_runs], "parallel-run outbounds")
        if self.decommission:
            if self.hypercare != "closed_green":
                raise ValueError(f"decommission is refused while hypercare is {self.hypercare}; "
                                 "it follows cutover and a hypercare closed green")
            orders = [d.order for d in self.decommission]
            if orders != list(range(1, len(orders) + 1)):
                raise ValueError(f"decommission items must be in order 1..n, got {orders}")
        people = [s.user_id for s in self.sign_off if s.user_id]
        if _dupes(people):
            raise ValueError("one person holds both release sign-off slots; the release needs two people")
        _require_unique([s.role for s in self.sign_off], "sign-off roles")
        return self


class CutoverPacket(_Envelope):
    agent_id: Literal["deployment_modernization"] = "deployment_modernization"
    artifact: Literal["cutover_artifacts"] = "cutover_artifacts"
    payload: CutoverPayload


#: Packet name → model. The name is the fixture/schema file stem.
PACKETS: dict[str, type[_Envelope]] = {
    "brief": BriefPacket,
    "assessment": AssessmentPacket,
    "design": DesignPacket,
    "plan": PlanPacket,
    "baseline": BaselinePacket,
    "migration_record": MigrationRecordPacket,
    "review": ReviewPacket,
    "security_report": SecurityPacket,
    "equivalence_results": EquivalencePacket,
    "cutover_plan": CutoverPacket,
}
