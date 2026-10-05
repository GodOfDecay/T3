import { z } from "zod";

/**
 * Track 3 (Code Modernization) — the shapes its first two agents record.
 *
 * Mirrors `backend/shared/models/artifacts.py` (MigrationIntentArtifact,
 * DiscoveryArtifact) and `discovery_agent/analysis/assessment.py`. Tolerant on
 * purpose — every collection defaults to empty — because these are read back from a
 * JSONB column a newer agent may have written with an extra field or an older one
 * without a newer field; a strict parse would blank the whole page over one of them.
 */

const strings = z.array(z.string()).default([]);
const text = z.string().default("");

/* Version 2 of the brief (structured sections). Every part defaults to empty, so a
   version-1 brief parses and renders through the same view. */
const BriefDriver = z.object({ category: z.string().default("other"), title: text, detail: text });
const BriefLayer = z.object({
  layer: text, current: text, current_status: text, target: text, change_type: text, modules: strings,
});
const BriefRecommendation = z.object({
  summary: text,
  recommended_by: z.string().default("agent"),
  rationale: strings,
  alternatives: z.array(z.object({ option: text, why_not: text })).default([]),
});
const BriefModuleChange = z.object({
  module: text, path: text, current: text, current_status: text, target: text,
  change_type: text, changes: strings, effort: text,
});
const BriefTradeOff = z.object({ decision: text, gain: text, cost: text });
const BriefMilestone = z.object({ date: text, label: text, kind: z.string().default("other") });
/** What a success measure is about (research §6.1): Migration Strategy turns the
 *  `equivalence` and `performance` ones into equivalence criteria. Null on a brief recorded
 *  before `kind` existed — shown as "not yet classified", never guessed. */
export const MEASURE_KINDS = ["equivalence", "performance", "security", "schedule", "cost"] as const;
export type MeasureKind = (typeof MEASURE_KINDS)[number];
const BriefMeasure = z.object({
  metric: text, current: text, target: text,
  kind: z.enum(MEASURE_KINDS).nullable().catch(null).default(null),
});

export const MigrationIntentBrief = z.object({
  system_name: z.string().default(""),
  goal: text,
  business_drivers: strings,
  drivers: z.array(BriefDriver).default([]),
  layers: z.array(BriefLayer).default([]),
  recommendation: BriefRecommendation.nullable().default(null),
  module_changes: z.array(BriefModuleChange).default([]),
  trade_offs: z.array(BriefTradeOff).default([]),
  deadline: text,
  budget: text,
  /** Phase F: when a cutover may take the system down, and where the data must stay. */
  downtime_window: text,
  data_residency: text,
  milestones: z.array(BriefMilestone).default([]),
  success_measures: z.array(BriefMeasure).default([]),
  current_state: z.object({ stack: z.string().default(""), description: z.string().default("") })
    .default({ stack: "", description: "" }),
  target_state: z.object({ stack: z.string().default(""), description: z.string().default("") })
    .default({ stack: "", description: "" }),
  in_scope: strings,
  out_of_scope: strings,
  constraints: strings,
  /** Interfaces, files and reports the user said must not change — in THEIR words (the
   *  record tool checks them against the conversation). Target Architecture turns each
   *  into a contract (CT-xx). */
  must_not_change: strings,
  /** False when the wording could NOT be checked against the conversation — then the page
   *  must not call it the user's own words. Null on older briefs. */
  must_not_change_verified: z.boolean().nullable().default(null),
  success_criteria: strings,
  stakeholders: z.array(z.object({ name: z.string(), role: z.string().default("") })).default([]),
  assumptions: strings,
  risks: strings,
  open_questions: strings,
  legacy_repository: z
    .object({
      provider: z.string().default(""),
      project: z.string().default(""),
      name: z.string().default(""),
      url: z.string().default(""),
    })
    .nullable()
    .default(null),
  recorded_at: z.string().nullable().default(null),
});
export type MigrationIntentBrief = z.infer<typeof MigrationIntentBrief>;
export type BriefDriver = z.infer<typeof BriefDriver>;
export type BriefLayer = z.infer<typeof BriefLayer>;
export type BriefModuleChange = z.infer<typeof BriefModuleChange>;
export type BriefMilestone = z.infer<typeof BriefMilestone>;

export const MigrationTier = z.enum(["mechanical", "llm_assisted", "manual"]);
export type MigrationTier = z.infer<typeof MigrationTier>;

export const RuntimeStatus = z.enum(["eol", "approaching", "legacy", "supported", "unknown"]);
export type RuntimeStatus = z.infer<typeof RuntimeStatus>;

const Vulnerability = z.object({
  cve: z.string().nullable().optional(),
  severity: z.string().nullable().optional(),
  package: z.string().nullable().optional(),
  installed_version: z.string().nullable().optional(),
  fixed_version: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
});

export const AssessedDependency = z.object({
  name: z.string(),
  version: z.string().default(""),
  kind: z.string().default("package"),
  status: z.string().default("ok"),
  note: z.string().default(""),
  vulnerabilities: z.array(Vulnerability).default([]),
});
export type AssessedDependency = z.infer<typeof AssessedDependency>;

export const RiskFactor = z.object({
  factor: z.string(),
  points: z.number(),
  detail: z.string().default(""),
  /** False when the input was never measured (no vulnerability scan ran): the factor
   *  contributes nothing and must read "not measured", never "+0" (Lessons R39). */
  measured: z.boolean().default(true),
});

export const AssessedModule = z.object({
  /** Stable within a commit (numbered by path), cited by every later agent. Empty on an
   *  assessment recorded before ids existed (schema 1). */
  id: z.string().default(""),
  name: z.string(),
  path: z.string(),
  ecosystem: z.string(),
  loc: z.number().default(0),
  files: z.number().default(0),
  /** Third-party front-end files (jQuery, Bootstrap, bundles): counted as files, not LOC. */
  vendored_files: z.number().default(0),
  has_tests: z.boolean().default(false),
  runtime: z.object({
    name: z.string().default(""),
    version: z.string().default(""),
    status: RuntimeStatus.catch("unknown"),
    eol_date: z.string().nullable().default(null),
    note: z.string().default(""),
  }),
  dependencies: z.array(AssessedDependency).default([]),
  depends_on: strings,
  dependents: strings,
  blockers: strings,
  risk: z.object({
    score: z.number(),
    tier: MigrationTier,
    factors: z.array(RiskFactor).default([]),
  }),
});
export type AssessedModule = z.infer<typeof AssessedModule>;

export const DiscoveryAssessment = z.object({
  schema_version: z.number(),
  generated_at: z.string(),
  as_of: z.string().default(""),
  target_stack: z.string().default(""),
  repository: z.object({
    url: z.string().default(""),
    branch: z.string().default(""),
    commit: z.string().default(""),
    provider: z.string().default(""),
    name: z.string().default(""),
  }),
  summary: z.object({
    module_count: z.number(),
    file_count: z.number().default(0),
    loc: z.number().default(0),
    vendored_files: z.number().default(0),
    languages: z.record(z.string(), z.number()).default({}),
    ecosystems: strings,
    tier_counts: z.object({
      mechanical: z.number().default(0),
      llm_assisted: z.number().default(0),
      manual: z.number().default(0),
    }),
    risk: z.object({ average: z.number().default(0), max: z.number().default(0) }),
    flag_counts: z.object({
      eol: z.number().default(0),
      deprecated: z.number().default(0),
      vulnerable: z.number().default(0),
    }),
  }),
  modules: z.array(AssessedModule),
  flags: z.object({
    eol: z.array(z.object({
      module: z.string(), runtime: z.string(), status: z.string(),
      eol_date: z.string().nullable().default(null), note: z.string().default(""),
    })).default([]),
    deprecated: z.array(z.object({
      module: z.string(), package: z.string(), version: z.string().default(""), reason: z.string(),
    })).default([]),
    vulnerable: z.array(z.object({
      module: z.string(), package: z.string().nullable().optional(),
      version: z.string().nullable().optional(), cve: z.string().nullable().optional(),
      severity: z.string().nullable().optional(), fixed_version: z.string().nullable().optional(),
      title: z.string().nullable().optional(),
    })).default([]),
  }),
  scanners: z.object({ trivy: z.string().default("skipped"), note: z.string().default("") })
    .default({ trivy: "skipped", note: "" }),
  /** A POINTER once Equivalence Testing accepts a baseline: {status: "captured", baselines: ["BL-01"]}. */
  golden_master: z.object({ status: z.string(), note: z.string().default(""), baselines: strings })
    .default({ status: "not_captured", note: "", baselines: [] }),
  /** What the code alone cannot tell — questions for Target Architecture (research §6.2). */
  not_assessable_statically: z.array(z.object({
    topic: z.string().default(""), modules: strings, question: z.string(),
  })).default([]),
});
export type DiscoveryAssessment = z.infer<typeof DiscoveryAssessment>;

/* ── Target Architecture (Phase E) ─────────────────────────────────────────────
   Mirrors `TargetDesignArtifact` (backend/shared/models/artifacts.py): the hand-over packet's
   DesignPayload plus what the record tool adds (sources, module paths, inventory totals, notes).
   Tolerant like the rest: enums fall back rather than blanking the page over one value. */

export const MIGRATION_PATTERNS = [
  "in_place_upgrade", "strangler_fig", "branch_by_abstraction", "parallel_run",
  "rewrite", "replatform", "retire", "keep",
] as const;
export type MigrationPattern = (typeof MIGRATION_PATTERNS)[number];

const DesignLayer = z.object({ layer: text, today: text, target: text, modules: strings });
const DesignedModule = z.object({
  module_id: z.string(),
  module: text,
  tier: MigrationTier.catch("llm_assisted"),
  risk_score: z.number().default(0),
  patterns: z.array(z.string()).default([]),
  rationale: text,
  adr_ids: strings,
  contract_ids: strings,
});
export type DesignedModule = z.infer<typeof DesignedModule>;
const FrozenContract = z.object({
  id: z.string(),
  name: text,
  kind: z.string().default("http"),
  legacy_location: text,
  consumers: strings,
  proof: text,
  status: z.enum(["confirmed", "proposed"]).catch("proposed"),
  brief_item: z.string().nullable().default(null),
});
export type FrozenContract = z.infer<typeof FrozenContract>;
const Trap = z.object({ id: z.string(), change: text, affects: strings, where: text, effect: text, contract_ids: strings });
export type DesignTrap = z.infer<typeof Trap>;
const Adr = z.object({
  id: z.string(), title: text, context: text, options: strings, decision: text, consequences: text,
  modules: strings, contracts: strings,
});
export type DesignAdr = z.infer<typeof Adr>;

export const TargetDesign = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  summary: text,
  layers: z.array(DesignLayer).default([]),
  modules: z.array(DesignedModule).default([]),
  interop: z.object({ routing: text, data: text, shared_libraries: text, jobs: text, identity: text })
    .partial().default({}),
  ordering_constraints: strings,
  frozen_contracts: z.array(FrozenContract).default([]),
  data_migration: z.object({
    source: text, target: text, method: text, behaviour_changes: strings, cutover: text,
  }).nullable().default(null),
  nfr: z.array(z.object({ measure: text, target: text, source: z.string().default("design") })).default([]),
  security_design: strings,
  traps: z.array(Trap).default([]),
  adrs: z.array(Adr).default([]),
  diagrams: z.array(z.object({ title: text, mermaid: text })).default([]),
  departures_from_brief: z.array(z.object({ brief_said: text, design_says: text, adr_id: text })).default([]),
  open_questions: strings,
  resolved_questions: z.array(z.object({ question: text, answer: text, source: z.string().default("user") }))
    .default([]),
  sources: z.object({
    brief: z.object({ version: z.number().nullable().default(null), status: z.string().default("") })
      .partial().nullable().default(null),
    assessment: z.object({
      version: z.number().nullable().default(null), status: z.string().default(""),
      commit: z.string().nullable().default(null), repository: z.string().nullable().default(null),
    }).partial().nullable().default(null),
    checkout_commit: z.string().nullable().default(null),
  }).partial().default({}),
  module_paths: z.record(z.string(), z.string()).default({}),
  interfaces: z.object({
    commit: z.string().nullable().default(null),
    counts: z.record(z.string(), z.number()).default({}),
    total: z.number().default(0),
  }).nullable().default(null),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type TargetDesign = z.infer<typeof TargetDesign>;

/* ── Migration Strategy (Phase F) ──────────────────────────────────────────────
   Mirrors `StrategyArtifact`: the hand-over packet's PlanPayload plus what the record tool
   computed (placements, the proposed order, the calendar and effort checks). */

const PlanWave = z.object({
  id: z.string(),
  name: text,
  modules: strings,
  patterns: z.record(z.string(), z.array(z.string())).default({}),
  starts: text,
  ends: text,
  date_status: z.enum(["given", "proposed"]).catch("proposed"),
  entry_criteria: strings,
  exit_criteria: strings,
  parallel_run: z.object({
    required: z.boolean().default(false), period: z.string().nullable().default(null),
    system_of_record: z.string().default("legacy"),
  }).default({ required: false, period: null, system_of_record: "legacy" }),
  cutover_window: z.string().nullable().default(null),
  rollback: z.object({ trigger: text, method: text, max_time: z.string().nullable().default(null) })
    .default({ trigger: "", method: "", max_time: null }),
  owner: z.string().nullable().default(null),
  order_reason: text,
});
export type PlanWave = z.infer<typeof PlanWave>;

const PlanCriterion = z.object({
  id: z.string(),
  module_id: z.string(),
  protects: strings,
  protects_measures: strings,
  observable: text,
  input_set: text,
  comparison: z.string().default("exact"),
  normalization: z.array(z.object({ field: text, rule: text, reason: text })).default([]),
  threshold: z.string().nullable().default(null),
});
export type PlanCriterion = z.infer<typeof PlanCriterion>;

const CalendarItem = z.object({
  conflict: text, impact: text, options: strings,
  resolution: z.string().nullable().default(null), ref: z.string().nullable().default(null),
});

export const MigrationPlan = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  summary: text,
  waves: z.array(PlanWave).default([]),
  order_exceptions: z.array(z.object({ module_id: z.string(), depends_on: z.string(), reason: text, adr_id: text }))
    .default([]),
  equivalence_criteria: z.array(PlanCriterion).default([]),
  baseline_plan: z.array(z.object({
    ec_id: z.string(), inputs: text, environment: text, data_source: text, masking: text, due: text,
  })).default([]),
  freeze_policy: z.object({ from: text, allowed: text, carry_forward: text })
    .default({ from: "", allowed: "", carry_forward: "" }),
  critical_path: strings,
  calendar_conflicts: z.array(CalendarItem).default([]),
  raid: z.object({
    risks: z.array(z.object({ risk: text, evidence: text, mitigation: text })).default([]),
    assumptions: strings, issues: strings, dependencies: strings,
  }).default({ risks: [], assumptions: [], issues: [], dependencies: [] }),
  effort: z.array(z.object({ wave: z.string(), band: text, basis: text })).default([]),
  budget_fit: text,
  sources: z.record(z.string(), z.object({
    version: z.number().nullable().default(null), status: z.string().default(""),
  }).partial().passthrough().nullable()).default({}),
  placements: z.array(z.object({ module_id: z.string(), wave: z.string(), ec_ids: strings })).default([]),
  proposed_order: z.object({
    order: z.array(z.object({
      step: z.number(), level: z.number(), modules: strings, names: strings, max_risk: z.number().default(0),
      cycle: z.boolean().default(false), depends_on: strings,
    })).default([]),
    kept: strings,
    cycles: z.array(strings).default([]),
  }).nullable().default(null),
  calendar_checked: z.array(z.object({ ref: z.string(), conflict: text, impact: text })).default([]),
  effort_table: z.object({
    modules: z.array(z.object({ module_id: z.string(), name: z.string().nullable().default(null), band: text,
      basis: text })).default([]),
    waves: z.array(z.object({ wave: z.string(), band: text, basis: text })).default([]),
    total_band: text,
  }).nullable().default(null),
  brief_dates: z.object({
    deadline: z.string().nullable().default(null),
    freeze_from: z.string().nullable().default(null),
    downtime_window: z.string().nullable().default(null),
    budget: z.string().nullable().default(null),
    milestones: z.array(z.object({ date: z.string(), label: z.string(), kind: z.string().default("other") }))
      .nullable().transform((m) => m ?? []).default([]),
  }).partial().default({}),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type MigrationPlan = z.infer<typeof MigrationPlan>;

/* ── Equivalence Testing, Baseline mode (Phase G) ──────────────────────────────
   Mirrors `EquivalenceArtifact`: the hand-over packet's BaselinePayload plus what the record tool
   set (sources, the capture, the mapping, per-scenario counts and MASKED noise, placements). No
   recording is ever in it — field names, counts and shapes like "<timestamp>" only. */

const Shapes = z.record(z.string(), z.array(z.string())).default({});

export const BaselineScenario = z.object({
  id: z.string(),
  kind: z.string().default("http"),
  cases: z.number().nullable().default(null),
  describes: text,
  varying: z.record(z.string(), z.number()).nullable().transform((v) => v ?? {}).default({}),
  examples: Shapes.nullable().transform((v) => v ?? {}),
});
export type BaselineScenario = z.infer<typeof BaselineScenario>;

export const Baseline = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  mode: z.string().default("baseline"),
  baselines: z.array(z.object({
    id: z.string(), ec_ids: strings, module_id: z.string(), count: z.number(), unit: z.string(),
    sha256: z.string(), region: text, noise_fields: strings, captured_at: z.string().nullable().default(null),
  })).default([]),
  noise: z.array(z.object({
    ec_id: z.string(), runs_compared: z.number().default(2), varying_fields: strings, covered_by_rule: strings,
  })).default([]),
  rule_proposals: z.array(z.object({ ec_id: z.string(), field: z.string(), rule: z.string(), evidence: text })).default([]),
  stubs: strings,
  not_captured: z.array(z.object({ ec_id: z.string(), reason: z.string() })).default([]),
  sources: z.object({
    plan: z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial(),
    design: z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial(),
  }).partial().default({}),
  capture: z.object({
    id: z.string().nullable(), startedAt: z.string().nullable(), finishedAt: z.string().nullable(),
    imageId: z.string().nullable(), commit: z.string().nullable(), profileSource: z.string().nullable(),
  }).partial().default({}),
  mapping: z.record(z.string(), strings).default({}),
  scenarios: z.array(BaselineScenario).default([]),
  placements: z.array(z.object({ module_id: z.string(), baseline_ids: strings })).default([]),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type Baseline = z.infer<typeof Baseline>;

export const Capture = z.object({
  id: z.string(),
  status: z.enum(["running", "complete", "failed"]).catch("failed"),
  startedAt: z.string().nullable().default(null),
  finishedAt: z.string().nullable().default(null),
  error: z.string().nullable().default(null),
  planVersion: z.number().nullable().default(null),
  commit: z.string().nullable().default(null),
  mapping: z.record(z.string(), strings).nullable().transform((v) => v ?? {}),
  scenarios: z.array(BaselineScenario.pick({ id: true, kind: true, cases: true, describes: true }))
    .nullable().transform((v) => v ?? []),
  keep: z.boolean().nullable().transform((v) => v ?? false),
});
export type Capture = z.infer<typeof Capture>;

export const CaptureList = z.object({ projectId: z.string(), captures: z.array(Capture).default([]) });
export type CaptureList = z.infer<typeof CaptureList>;

/* ── Migration Development (Phase H) ──────────────────────────────────────────
   Mirrors `MigrationArtifact`: ONE module's migration record — the hand-over packet's
   MigrationRecordPayload plus what the record tool set from the workspace (the module's plan, the
   commits by concern, the head, tests, lint and the equivalence preview). Never code. */

const Check = z.object({ status: z.string(), note: text, head: text }).partial().nullable().default(null);

export const Migration = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  module_id: z.string(),
  outcome: z.enum(["ready_for_review", "build_failed", "blocked"]).catch("build_failed"),
  legacy_module_path: z.string(),
  target_branch: z.string().nullable().default(null),
  pr_url: z.string().nullable().default(null),
  recipes: z.array(z.object({ tool: z.string(), version: z.string(), args: text })).default([]),
  file_map: z.array(z.object({
    legacy_path: z.string(), disposition: z.enum(["mapped", "merged", "dropped"]).catch("mapped"),
    target_path: z.string().nullable().default(null), reason: z.string().nullable().default(null),
  })).default([]),
  llm_rewritten: z.array(z.object({ file: z.string(), reason: z.string() })).default([]),
  traps_handled: z.record(z.string(), z.string()).default({}),
  vault_references: strings,
  build: z.object({
    status: z.enum(["green", "red", "not_run"]).catch("not_run"), rounds: z.number().default(0),
    failing: z.string().nullable().default(null),
  }).default({ status: "not_run", rounds: 0, failing: null }),
  manual_follow_ups: strings,
  handoff_note: z.string().nullable().default(null),
  module: z.object({
    name: z.string().nullable(), tier: z.string().nullable(), patterns: strings, wave: z.string().nullable(),
    baseline_ids: strings, trap_ids: strings, target_runtime: z.string().nullable(), legacy_runtime: z.string().nullable(),
    ecosystem: z.string().nullable(),
  }).partial().default({}),
  sources: z.object({
    design: z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial(),
    plan: z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial(),
    baseline: z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial(),
  }).partial().default({}),
  base_branch: z.string().nullable().default(null),
  head_sha: z.string().nullable().default(null),
  commits: z.array(z.object({ sha: z.string(), subject: z.string() })).default([]),
  changed_files: strings,
  tests: Check,
  lint: Check,
  preview: z.object({
    headline: z.string(),
    scenarios: z.record(z.string(), z.object({
      cases: z.number().default(0), differences: z.record(z.string(), z.number()).default({}),
      examples: Shapes, ignored: strings,
    })).default({}),
    baseline_version: z.number().nullable().default(null),
  }).nullable().default(null),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type Migration = z.infer<typeof Migration>;

/* ── Equivalence Testing, Verify mode (Phase J) ─────────────────────────────────
   Mirrors `VerificationArtifact`: ONE module's verification — the packet's EquivalencePayload (criteria
   verdicts, differences, performance, rule proposals) plus what the tools set (the migration version and head
   verified, the baseline replayed, the module verdict, per-scenario field names). Shapes only, never values. */

export const Verification = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  mode: z.literal("verify"),
  module_id: z.string(),
  pr: text,
  baselines_replayed: z.array(z.object({ id: z.string(), version: z.number() })).default([]),
  criteria: z.array(z.object({
    ec_id: z.string(), verdict: z.enum(["passed", "failed", "open", "not_run"]).catch("not_run"),
    cases_compared: z.number().nullable().default(null), normalization_applied: strings,
  })).default([]),
  differences: z.array(z.object({
    id: z.string(), ec_id: z.string(),
    classification: z.enum(["regression", "normalization_gap", "accepted_change", "environment"]).catch("regression"),
    field: z.string(), cases: z.number(), masked_example: z.string(),
    likely_area: z.string().nullable().default(null), adr_id: z.string().nullable().default(null),
  })).default([]),
  performance: z.array(z.object({
    ec_id: z.string(), legacy_p95_ms: z.number().nullable().default(null), target_p95_ms: z.number().nullable().default(null),
    threshold_ms: z.number(),
  })).default([]),
  rule_proposals: z.array(z.object({ ec_id: z.string(), field: z.string(), rule: z.string(), evidence: z.string() })).default([]),
  runs: z.number().default(2),
  module_verdict: z.enum(["verified", "migrating", "open"]).catch("open"),
  migration_version: z.number().nullable().default(null),
  head_sha: z.string().nullable().default(null),
  baseline_version: z.number().nullable().default(null),
  module: z.object({ name: z.string().nullable(), legacy_path: z.string().nullable() }).partial().default({}),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type Verification = z.infer<typeof Verification>;

/* ── Migration Review and Security (Phase I) ──────────────────────────────────
   Mirror `MigrationReviewArtifact` and `ModernizationSecurityArtifact`: ONE module's review / security
   report — the hand-over packet's payload plus what the submit tool set (the migration version and head
   reviewed, the files the run opened, the API diff and anti-pattern scan; the scans, scanner hits, legacy
   baseline, carry-over and authz evidence). Never code, never a secret value. */

const Severity = z.enum(["critical", "high", "medium", "low", "info"]).catch("info");
const SurfaceItem = z.object({ kind: z.string(), name: z.string(), location: text, evidence: text, change: z.string().optional() });
const Hit = z.object({
  tool: z.string(), rule: z.string().nullable().default(null), title: text, severity: Severity,
  file: z.string().nullable().default(null), line: z.number().nullable().default(null),
  package: z.string().nullable().default(null), version: z.string().nullable().default(null),
  cve: z.string().nullable().default(null), origin: z.string().optional(), legacy_ref: z.string().nullable().optional(),
});
const Sources = z.record(z.string(), z.object({ version: z.number().nullable(), status: z.string().nullable() }).partial()).default({});

export const MigrationReview = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  module_id: z.string(),
  pr: text,
  summary: text,
  merge_recommendation: z.enum(["approve", "request_changes", "needs_discussion"]).catch("needs_discussion"),
  findings: z.array(z.object({
    id: z.string(), severity: Severity, category: z.string(), file: z.string(), line: z.number().nullable().default(null),
    legacy_file: z.string().nullable().default(null), legacy_line: z.number().nullable().default(null),
    description: z.string(), recommendation: z.string(), refs: strings, autofix_patch: z.string().nullable().default(null),
  })).default([]),
  equivalence_coverage: z.array(z.object({ ec_id: z.string(), status: z.string(), note: text })).default([]),
  contract_check: z.array(z.object({ ct_id: z.string(), status: z.string(), note: text })).default([]),
  trap_check: z.array(z.object({ tr_id: z.string(), status: z.string(), where: text })).default([]),
  traceability: z.array(z.object({ legacy_path: z.string(), target_path: z.string().nullable().default(null), status: z.string() })).default([]),
  known_debt: z.array(z.object({ pattern: z.string(), legacy_file: z.string(), note: text })).default([]),
  files_read: z.object({ target: strings, legacy: strings }).default({ target: [], legacy: [] }),
  migration_version: z.number().nullable().default(null),
  head_sha: z.string().nullable().default(null),
  legacy_commit: z.string().nullable().default(null),
  module: z.object({ name: z.string().nullable(), tier: z.string().nullable(), legacy_path: z.string().nullable() }).partial().default({}),
  sources: Sources,
  surface: z.object({
    removed: z.array(SurfaceItem).default([]), added: z.array(SurfaceItem).default([]),
    contracts: z.record(z.string(), z.array(SurfaceItem)).default({}),
    legacy_count: z.number().default(0), target_count: z.number().default(0),
  }).partial().default({}),
  antipatterns: z.object({
    target: z.array(z.object({ rule: z.string(), title: z.string(), severity: Severity, file: z.string(), line: z.number(),
      origin: z.string(), legacy_file: z.string().nullable().default(null) })).default([]),
    fixed: z.array(z.object({ rule: z.string(), title: z.string(), file: z.string(), line: z.number() })).default([]),
  }).partial().default({}),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type MigrationReview = z.infer<typeof MigrationReview>;

export const ModernizationSecurity = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  module_id: z.string(),
  pr: text,
  legacy_commit: text,
  scans: z.record(z.string(), z.string()).default({}),
  findings: z.array(z.object({
    id: z.string(), title: z.string(), severity: Severity, origin: z.enum(["carried_over", "introduced"]).catch("introduced"),
    legacy_ref: z.string().nullable().default(null), reachable: z.boolean().nullable().default(null),
    is_secret: z.boolean().default(false), cve: z.string().nullable().default(null), package: z.string().nullable().default(null),
    file: z.string().nullable().default(null), remediation_plan: z.string().nullable().default(null),
    remediation_due: z.string().nullable().default(null),
  })).default([]),
  fixed_from_legacy: z.array(z.object({ title: z.string(), cve: z.string().nullable().default(null),
    package: z.string().nullable().default(null), legacy_ref: z.string() })).default([]),
  contract_authz: z.array(z.object({ ct_id: z.string(), status: z.string(), note: text })).default([]),
  sbom: z.object({ components: z.number().nullable().default(null), vulnerabilities: z.number().nullable().default(null) })
    .default({ components: null, vulnerabilities: null }),
  verdict: z.enum(["FAIL", "CONDITIONAL", "PASS"]).catch("FAIL"),
  rationale: text,
  required_verdict: z.string().nullable().default(null),
  migration_version: z.number().nullable().default(null),
  head_sha: z.string().nullable().default(null),
  module: z.object({ name: z.string().nullable(), legacy_path: z.string().nullable() }).partial().default({}),
  sources: Sources,
  scanner_versions: z.record(z.string(), z.string()).default({}),
  scan_notes: z.record(z.string(), z.string()).default({}),
  target_hits: z.array(Hit).default([]),
  legacy_hits: z.array(Hit).default([]),
  legacy_cached: z.boolean().default(false),
  secret_carryover: z.array(z.object({ file: z.string(), line: z.number(), legacy_file: z.string() })).default([]),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type ModernizationSecurity = z.infer<typeof ModernizationSecurity>;

export const MigrationWorkspace = z.object({
  moduleId: z.string(),
  modulePath: text,
  branch: text,
  baseBranch: text,
  ecosystem: z.string().nullable().default(null),
  targetRuntime: z.string().nullable().default(null),
  commits: z.array(z.object({ sha: z.string(), concern: z.string(), message: text, files: z.number().nullable().default(null) })).default([]),
  recipes: z.array(z.object({ tool: z.string(), version: z.string(), files: z.number().default(0) })).default([]),
  builds: z.array(z.object({ round: z.number(), ok: z.boolean(), at: z.string().nullable().default(null) })).default([]),
  tests: z.string().nullable().default(null),
  lint: z.string().nullable().default(null),
  preview: z.string().nullable().default(null),
  pushed: z.object({ head: z.string(), at: z.string(), pr_url: z.string().nullable() }).nullable().default(null),
  openedAt: z.string().nullable().default(null),
});
export type MigrationWorkspace = z.infer<typeof MigrationWorkspace>;

export const MigrationWorkspaceList = z.object({ projectId: z.string(), workspaces: z.array(MigrationWorkspace).default([]) });
export type MigrationWorkspaceList = z.infer<typeof MigrationWorkspaceList>;

export const LegacyInterface = z.object({
  kind: z.string(),
  direction: z.string(),
  name: z.string(),
  location: z.string(),
  module: z.string().default(""),
  evidence: z.string().default(""),
});
export type LegacyInterface = z.infer<typeof LegacyInterface>;

export const LegacyInterfaces = z.object({
  projectId: z.string(),
  status: z.enum(["none", "ready"]).catch("none"),
  repository: z.string().nullable().optional(),
  inventory: z.object({
    commit: z.string().default(""),
    counts: z.record(z.string(), z.number()).default({}),
    total: z.number().default(0),
    truncated: z.boolean().default(false),
    items: z.array(LegacyInterface).default([]),
  }).nullable().default(null),
});
export type LegacyInterfaces = z.infer<typeof LegacyInterfaces>;

/** The read endpoints' envelope: the newest run holding a value, or nulls. */
export function stagePayload<T extends z.ZodTypeAny>(payload: T) {
  return z.object({
    projectId: z.string(),
    runId: z.string().nullable(),
    updatedAt: z.string().nullable(),
    payload: payload.nullable(),
  });
}

export const MigrationIntentResponse = stagePayload(MigrationIntentBrief);
export type MigrationIntentResponse = z.infer<typeof MigrationIntentResponse>;
export const DiscoveryResponse = stagePayload(DiscoveryAssessment);
export type DiscoveryResponse = z.infer<typeof DiscoveryResponse>;

/* ── The project's pulled legacy code (both Track 3 pages) ─────────────────── */

export const LegacyCodeStatus = z.enum(["none", "pulling", "ready", "failed"]);
export type LegacyCodeStatus = z.infer<typeof LegacyCodeStatus>;

export const LegacyCodeModule = z.object({
  name: z.string(),
  path: z.string().default(""),
  ecosystem: z.string().default(""),
  runtime: z.string().default(""),
  runtimeStatus: z.string().default("unknown"),
  eolDate: z.string().nullable().default(null),
  loc: z.number().default(0),
  files: z.number().default(0),
  hasTests: z.boolean().default(false),
  platformFeatures: strings,
  dependsOn: strings,
  packageCount: z.number().default(0),
});
export type LegacyCodeModule = z.infer<typeof LegacyCodeModule>;

/** The last GOOD pull — what the project's checkout holds right now. */
export const LegacyCodePull = z.object({
  url: z.string(),
  branch: z.string().default(""),
  commit: z.string().default(""),
  provider: z.string().default(""),
  name: z.string().default(""),
  pulledBy: z.string().default(""),
  pulledAt: z.string().default(""),
  profile: z
    .object({
      summary: z
        .object({
          modules: z.number().default(0),
          files: z.number().default(0),
          loc: z.number().default(0),
          vendoredFiles: z.number().default(0),
          languages: z.record(z.string(), z.number()).default({}),
          ecosystems: strings,
          endOfLife: z.number().default(0),
          deprecatedPackages: z.number().default(0),
        })
        .partial()
        .default({}),
      modules: z.array(LegacyCodeModule).default([]),
    })
    .nullable()
    .default(null),
});
export type LegacyCodePull = z.infer<typeof LegacyCodePull>;

/** `status` is the latest ATTEMPT; `pull` is the last good one (kept when a re-pull fails). */
export const LegacyCodeRecord = z.object({
  projectId: z.string(),
  status: LegacyCodeStatus.catch("none"),
  request: z
    .object({
      url: z.string().default(""),
      branch: z.string().default(""),
      requestedBy: z.string().default(""),
      startedAt: z.string().nullable().default(null),
    })
    .nullable()
    .default(null),
  error: z.string().default(""),
  pull: LegacyCodePull.nullable().default(null),
});
export type LegacyCodeRecord = z.infer<typeof LegacyCodeRecord>;

/** What the project's Azure DevOps / GitHub connection can see, for the Pull dialog. */
export const LegacyRepositories = z.object({
  provider: z.string().default(""),
  projects: z.array(z.string()).optional(),
  repositories: z
    .array(z.object({ name: z.string(), url: z.string().default(""), defaultBranch: z.string().default("") }))
    .optional(),
  problem: z.string().default(""),
});
export type LegacyRepositories = z.infer<typeof LegacyRepositories>;
